"""Unit tests for :mod:`tit.opt.roi_spec` (pure-Python ROI-spec resolution)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

from tit.opt import roi_spec
from tit.opt.config import FlexConfig


def _mock_read_annot(monkeypatch, names: list[str]):
    """Install a ``nibabel.freesurfer.io.read_annot`` mock returning *names*."""
    nfs_mock = sys.modules["nibabel.freesurfer"]
    fsio_mock = MagicMock()
    fsio_mock.read_annot.return_value = (None, None, names)
    monkeypatch.setitem(sys.modules, "nibabel.freesurfer.io", fsio_mock)
    monkeypatch.setattr(nfs_mock, "io", fsio_mock, raising=False)
    return fsio_mock


class TestResolveAtlasNameForSubject:
    def test_prepends_subject_id(self):
        assert roi_spec.resolve_atlas_name_for_subject("DK40", "001") == "001_DK40"


class TestParseRegionNames:
    def test_parses_hemisphere_prefixed_names(self):
        assert roi_spec.parse_region_names("lh.precentral, rh.superiorfrontal") == [
            ("lh", "precentral"),
            ("rh", "superiorfrontal"),
        ]

    def test_ignores_blank_entries(self):
        assert roi_spec.parse_region_names("lh.precentral, , ") == [
            ("lh", "precentral")
        ]

    def test_rejects_missing_hemisphere_prefix(self):
        with pytest.raises(ValueError, match="hemisphere-prefixed"):
            roi_spec.parse_region_names("precentral")

    def test_rejects_unknown_hemisphere(self):
        with pytest.raises(ValueError, match="'lh' or 'rh'"):
            roi_spec.parse_region_names("xx.precentral")


class TestCorticalAtlasRoi:
    def test_single_region_scalar_fields(self, tmp_path, monkeypatch):
        seg_dir = tmp_path
        (seg_dir / "lh.001_DK40.annot").touch()
        (seg_dir / "rh.001_DK40.annot").touch()
        _mock_read_annot(monkeypatch, ["unknown", "precentral", "superiorfrontal"])

        roi = roi_spec.build_cortical_atlas_roi(
            subject_id="001",
            seg_dir=str(seg_dir),
            atlas_display="DK40",
            regions=[("lh", "precentral")],
        )
        assert isinstance(roi, FlexConfig.AtlasROI)
        assert roi.label == 1
        assert roi.hemisphere == "lh"
        assert roi.atlas_path == str(seg_dir / "lh.001_DK40.annot")

    def test_multi_region_union_produces_parallel_lists(self, tmp_path, monkeypatch):
        seg_dir = tmp_path
        (seg_dir / "lh.001_DK40.annot").touch()
        (seg_dir / "rh.001_DK40.annot").touch()
        _mock_read_annot(monkeypatch, ["unknown", "precentral", "superiorfrontal"])

        roi = roi_spec.get_roi_spec(
            "atlas",
            subject_id="001",
            seg_dir=str(seg_dir),
            atlas_display="DK40",
            regions=[("lh", "precentral"), ("rh", "superiorfrontal")],
        )
        assert roi.label == [1, 2]
        assert roi.hemisphere == ["lh", "rh"]
        assert roi.atlas_path == [
            str(seg_dir / "lh.001_DK40.annot"),
            str(seg_dir / "rh.001_DK40.annot"),
        ]

    def test_unresolvable_region_raises(self, tmp_path, monkeypatch):
        seg_dir = tmp_path
        (seg_dir / "lh.001_DK40.annot").touch()
        _mock_read_annot(monkeypatch, ["unknown", "precentral"])

        with pytest.raises(ValueError, match="Could not resolve"):
            roi_spec.build_cortical_atlas_roi(
                subject_id="001",
                seg_dir=str(seg_dir),
                atlas_display="DK40",
                regions=[("lh", "nonexistent")],
            )

    def test_no_annot_files_gives_empty_map(self, tmp_path):
        assert roi_spec.resolve_cortical_region_index_map(str(tmp_path), "DK40") == {}


class TestSphericalRoi:
    def test_single_sphere_collapses_to_scalars(self):
        roi = roi_spec.get_roi_spec(
            "spherical",
            subject_id="001",
            seg_dir="",
            centers=[(1.0, 2.0, 3.0)],
            radii=[5.0],
        )
        assert (roi.x, roi.y, roi.z, roi.radius) == (1.0, 2.0, 3.0, 5.0)
        assert roi.volumetric is False

    def test_multi_sphere_union_stays_lists(self):
        roi = roi_spec.get_roi_spec(
            "spherical",
            subject_id="001",
            seg_dir="",
            centers=[(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
            radii=[5.0, 6.0],
            volumetric=True,
            sphere_tissues="WM",
        )
        assert roi.x == [1.0, 4.0]
        assert roi.tissues == "WM"

    def test_non_volumetric_forces_gm_tissues(self):
        roi = roi_spec.build_spherical_roi(
            centers=[(0.0, 0.0, 0.0)], radii=[1.0], volumetric=False, tissues="WM"
        )
        assert roi.tissues == "GM"

    def test_missing_centers_raises(self):
        with pytest.raises(ValueError, match="requires centers and radii"):
            roi_spec.get_roi_spec("spherical", subject_id="001", seg_dir="")


class TestVolumeAtlasPathResolution:
    def test_subject_space_labeling(self):
        path = roi_spec.resolve_volume_atlas_path(
            subject_id="001",
            seg_dir="/proj/m2m_001/segmentation",
            freesurfer_mri_dir="/proj/freesurfer/001/mri",
            atlas_filename="labeling.nii.gz",
            atlas_space="subject",
        )
        assert path == "/proj/m2m_001/segmentation/labeling.nii.gz"

    def test_subject_space_freesurfer_atlas(self):
        path = roi_spec.resolve_volume_atlas_path(
            subject_id="001",
            seg_dir="/proj/m2m_001/segmentation",
            freesurfer_mri_dir="/proj/freesurfer/001/mri",
            atlas_filename="aparc.DKTatlas+aseg.mgz",
            atlas_space="subject",
        )
        assert path == "/proj/freesurfer/001/mri/aparc.DKTatlas+aseg.mgz"

    def test_mni_space_uses_mni_atlas_dir(self):
        path = roi_spec.resolve_volume_atlas_path(
            subject_id="001",
            seg_dir="/proj/m2m_001/segmentation",
            freesurfer_mri_dir="",
            atlas_filename="CIT168.nii.gz",
            atlas_space="mni",
        )
        assert path.endswith("/resources/atlas/CIT168.nii.gz")


class TestSubcorticalRoi:
    def test_build_subcortical_roi(self):
        roi = roi_spec.build_subcortical_roi(
            atlas_path="/proj/freesurfer/mri/aseg.mgz", labels=[17], tissues="both"
        )
        assert isinstance(roi, FlexConfig.SubcorticalROI)
        assert roi.label == 17
        assert roi.tissues == "both"
        assert roi.atlas_space == "subject"

    def test_get_roi_spec_subcortical_resolves_path_from_filename(self):
        roi = roi_spec.get_roi_spec(
            "subcortical",
            subject_id="001",
            seg_dir="/proj/m2m_001/segmentation",
            freesurfer_mri_dir="/proj/freesurfer/001/mri",
            volume_atlas_filename="aseg.mgz",
            volume_atlas_space="subject",
            subcortical_labels=[17, 18],
        )
        assert roi.atlas_path == "/proj/freesurfer/001/mri/aseg.mgz"
        assert roi.label == [17, 18]

    def test_missing_labels_raises(self):
        with pytest.raises(ValueError, match="requires subcortical_labels"):
            roi_spec.get_roi_spec(
                "subcortical",
                subject_id="001",
                seg_dir="",
                volume_atlas_path="/x.nii.gz",
                subcortical_labels=[],
            )

    def test_missing_path_and_filename_raises(self):
        with pytest.raises(
            ValueError, match="volume_atlas_path or volume_atlas_filename"
        ):
            roi_spec.get_roi_spec(
                "subcortical", subject_id="001", seg_dir="", subcortical_labels=[1]
            )


class TestGetRoiSpecDispatch:
    def test_unknown_roi_type_raises(self):
        with pytest.raises(ValueError, match="Unknown roi_type"):
            roi_spec.get_roi_spec("bogus", subject_id="001", seg_dir="")

    def test_cortical_alias_accepted(self, tmp_path, monkeypatch):
        seg_dir = tmp_path
        (seg_dir / "lh.001_DK40.annot").touch()
        _mock_read_annot(monkeypatch, ["unknown", "precentral"])
        roi = roi_spec.get_roi_spec(
            "cortical",
            subject_id="001",
            seg_dir=str(seg_dir),
            atlas_display="DK40",
            regions=[("lh", "precentral")],
        )
        assert isinstance(roi, FlexConfig.AtlasROI)


class TestResolveVolumeLabelNames:
    def test_sidecar_lut_wins_over_freesurfer_table(self, tmp_path):
        atlas_path = tmp_path / "custom_atlas.nii.gz"
        atlas_path.touch()
        lut_path = tmp_path / "custom_atlas_LUT.txt"
        lut_path.write_text("1 MyRegion 255 0 0\n2 OtherRegion 0 255 0\n")

        names = roi_spec.resolve_volume_label_names(str(atlas_path), atlas_space="mni")
        assert names == {1: "MyRegion", 2: "OtherRegion"}

    def test_labeling_lut_sidecar_in_subject_space(self, tmp_path):
        atlas_path = tmp_path / "labeling.nii.gz"
        atlas_path.touch()
        (tmp_path / "labeling_LUT.txt").write_text("5 Custom_Region 1 2 3\n")

        names = roi_spec.resolve_volume_label_names(
            str(atlas_path), atlas_space="subject"
        )
        assert names == {5: "Custom_Region"}

    def test_falls_back_to_bundled_freesurfer_lut(self, tmp_path, monkeypatch):
        atlas_path = tmp_path / "freesurfer" / "001" / "mri" / "aparc.DKTatlas+aseg.mgz"
        atlas_path.parent.mkdir(parents=True)
        atlas_path.touch()

        fake_img = MagicMock()
        fake_img.dataobj = np.array([[0, 17], [17, 8]])
        monkeypatch.setattr("nibabel.load", lambda path: fake_img, raising=False)

        names = roi_spec.resolve_volume_label_names(
            str(atlas_path), atlas_space="subject"
        )
        assert names[17] == "Left-Hippocampus"
        assert 0 not in names  # background dropped

    def test_unreadable_atlas_returns_empty_dict(self, tmp_path, monkeypatch):
        atlas_path = tmp_path / "freesurfer" / "001" / "mri" / "aparc.DKTatlas+aseg.mgz"
        atlas_path.parent.mkdir(parents=True)
        atlas_path.touch()

        def _raise(path):
            raise OSError("cannot read")

        monkeypatch.setattr("nibabel.load", _raise, raising=False)
        assert (
            roi_spec.resolve_volume_label_names(str(atlas_path), atlas_space="subject")
            == {}
        )

    def test_custom_mask_keeps_unknown_labels(self, tmp_path, monkeypatch):
        atlas_path = tmp_path / "masks" / "my_mask.nii.gz"
        atlas_path.parent.mkdir(parents=True)
        atlas_path.touch()

        fake_img = MagicMock()
        fake_img.dataobj = np.array([0, 99999])
        monkeypatch.setattr("nibabel.load", lambda path: fake_img, raising=False)

        names = roi_spec.resolve_volume_label_names(
            str(atlas_path), atlas_space="subject"
        )
        assert names[99999] == "Label 99999"
