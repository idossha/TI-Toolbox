"""Unit tests for tit.config_io — JSON serialization of config dataclasses."""

import json
import os

import pytest

from tit.config_io import serialize_config, write_config_json, read_config_json
from tit.opt.config import FlexConfig, ExConfig

# Convenience aliases for nested types
OptGoal = FlexConfig.OptGoal
FieldPostproc = FlexConfig.FieldPostproc
SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI
FlexElectrodeConfig = FlexConfig.ElectrodeConfig

# ── serialize_config ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSerializeConfig:
    def test_enum_values_serialized(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal=OptGoal.MEAN,
            postproc=FieldPostproc.MAX_TI,
            current_mA=2.0,
            electrode=FlexElectrodeConfig(),
            roi=SphericalROI(x=1, y=2, z=3),
        )
        data = serialize_config(config)
        assert data["goal"] == "mean"
        assert data["postproc"] == "max_TI"

    def test_spherical_roi_has_type_discriminator(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexElectrodeConfig(),
            roi=SphericalROI(x=10, y=20, z=30, radius=5.0, use_mni=True),
        )
        data = serialize_config(config)
        assert data["roi"]["_type"] == "SphericalROI"
        assert data["roi"]["x"] == 10
        assert data["roi"]["radius"] == 5.0
        assert data["roi"]["use_mni"] is True

    def test_atlas_roi_has_type_discriminator(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexElectrodeConfig(),
            roi=AtlasROI(atlas_path="/path/to/atlas.annot", label=5, hemisphere="lh"),
        )
        data = serialize_config(config)
        assert data["roi"]["_type"] == "AtlasROI"
        assert data["roi"]["atlas_path"] == "/path/to/atlas.annot"

    def test_subcortical_roi_has_type_discriminator(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexElectrodeConfig(),
            roi=SubcorticalROI(atlas_path="/vol.nii.gz", label=10, tissues="WM"),
        )
        data = serialize_config(config)
        assert data["roi"]["_type"] == "SubcorticalROI"
        assert data["roi"]["tissues"] == "WM"

    def test_nested_electrode_config(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexElectrodeConfig(
                shape="rect", dimensions=[10, 5], gel_thickness=3.0
            ),
            roi=SphericalROI(x=0, y=0, z=0),
        )
        data = serialize_config(config)
        assert data["electrode"]["shape"] == "rect"
        assert data["electrode"]["dimensions"] == [10, 5]

    def test_none_values_preserved(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexElectrodeConfig(),
            roi=SphericalROI(x=0, y=0, z=0),
        )
        data = serialize_config(config)
        assert data["non_roi"] is None
        assert data["thresholds"] is None
        assert data["max_iterations"] is None

    def test_pool_electrodes_discriminator(self):
        electrodes = ExConfig.PoolElectrodes(electrodes=["C3", "C4", "Cz"])
        data = serialize_config(electrodes)
        assert data["_type"] == "PoolElectrodes"

    def test_bucket_electrodes_discriminator(self):
        electrodes = ExConfig.BucketElectrodes(
            e1_plus=["C3"], e1_minus=["C4"], e2_plus=["Cz"], e2_minus=["Pz"]
        )
        data = serialize_config(electrodes)
        assert data["_type"] == "BucketElectrodes"

    def test_non_dataclass_passthrough(self):
        """serialize_config handles dicts by recursively serializing values."""
        result = serialize_config({"key": "value"})
        assert result == {"key": "value"}


# ── write/read round-trip ───────────────────────────────────────────────────


@pytest.mark.unit
class TestWriteReadRoundTrip:
    def test_flex_config_roundtrip(self, tmp_path):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp/project",
            goal=OptGoal.MAX,
            postproc=FieldPostproc.DIR_TI_NORMAL,
            current_mA=2.5,
            electrode=FlexElectrodeConfig(
                shape="ellipse", dimensions=[8, 8], gel_thickness=4.0
            ),
            roi=SphericalROI(x=-50, y=30, z=10, radius=15.0, use_mni=True),
            n_multistart=3,
            max_iterations=100,
        )
        path = write_config_json(config, prefix="test")
        try:
            assert os.path.isfile(path)
            data = read_config_json(path)
            assert data["subject_id"] == "001"
            assert data["goal"] == "max"
            assert data["postproc"] == "dir_TI_normal"
            assert data["roi"]["_type"] == "SphericalROI"
            assert data["roi"]["x"] == -50
            assert data["n_multistart"] == 3
        finally:
            os.unlink(path)

    def test_ex_config_roundtrip(self, tmp_path):
        config = ExConfig(
            subject_id="001",
            project_dir="/tmp/project",
            leadfield_hdf="test.hdf5",
            roi_name="my_roi.csv",
            electrodes=ExConfig.PoolElectrodes(electrodes=["C3", "C4", "Cz", "Pz"]),
            total_current=2.0,
            current_step=0.5,
        )
        path = write_config_json(config, prefix="test")
        try:
            data = read_config_json(path)
            assert data["electrodes"]["_type"] == "PoolElectrodes"
            assert data["electrodes"]["electrodes"] == ["C3", "C4", "Cz", "Pz"]
            assert data["total_current"] == 2.0
        finally:
            os.unlink(path)

    def test_json_is_valid(self):
        config = FlexConfig(
            subject_id="001",
            project_dir="/tmp",
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexElectrodeConfig(),
            roi=SphericalROI(x=0, y=0, z=0),
        )
        path = write_config_json(config)
        try:
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, dict)
        finally:
            os.unlink(path)
