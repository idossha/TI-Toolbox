"""Unit tests for the sub-cortical export mode of the ``blender`` job kind.

2.5.0 ran this mode inline on the Qt main thread, so it had no config dataclass, no runner module
and no test. This file covers the three things the migration to a job depends on:

- :class:`tit.blender.config.SubcorticalConfig` validating and round-tripping like every other
  registered config (the wider registry sweep lives in ``tests/test_config_schema.py``);
- the filename rule (``labels_10_49_clean`` / ``full_raw``) and the field-NIfTI lookup, which are
  what makes the outputs byte-identical to 2.5.0's;
- the wiring itself -- ``kind="blender"`` with ``_type="SubcorticalConfig"`` reaching
  ``tit.blender.__main__``'s dispatch, and ``routes/validate.py`` resolving it to the right class.
"""

import os

import pytest

from tit.blender.config import SubcorticalConfig
from tit.blender.subcortical_exporter import find_field_nifti, output_suffix
from tit.config_io import _discriminator_for, deserialize_config, serialize_config
from tit.jobs.kinds import command_for
from tit.server.routes.validate import cls_for

pytestmark = pytest.mark.unit


class TestSubcorticalConfig:
    def test_subject_only_is_enough(self):
        cfg = SubcorticalConfig(subject_id="ernie")
        assert cfg.simulation_name == ""
        assert cfg.labels == []
        assert cfg.field_name == "TI_max"
        assert cfg.clean_components is False

    def test_missing_subject_raises(self):
        with pytest.raises(ValueError, match="subject_id is required"):
            SubcorticalConfig(subject_id="  ")

    def test_empty_field_name_raises(self):
        with pytest.raises(ValueError, match="field_name is required"):
            SubcorticalConfig(subject_id="ernie", field_name="")

    def test_labels_are_coerced_to_int(self):
        # The GUI's own "10,49" text field parses to ints before it gets here, but a hand-written
        # config.json (or a JSON round trip through a float) must not silently produce "10.0".
        assert SubcorticalConfig(subject_id="ernie", labels=["10", 49]).labels == [10, 49]

    def test_non_integer_label_raises(self):
        with pytest.raises(ValueError, match="labels must be integers"):
            SubcorticalConfig(subject_id="ernie", labels=["thalamus"])

    def test_round_trips_with_its_discriminator(self):
        cfg = SubcorticalConfig(subject_id="ernie", simulation_name="sim1", labels=[10, 49])
        data = serialize_config(cfg)
        assert data["_type"] == "SubcorticalConfig" == _discriminator_for(SubcorticalConfig)
        data.pop("project_dir", None)
        assert deserialize_config(SubcorticalConfig, data) == cfg


class TestOutputSuffix:
    """The 2.5.0 filename rule, which decides every written file's name."""

    def test_no_labels_no_cleaning(self):
        assert output_suffix([], False) == "full_raw"

    def test_cleaning_only(self):
        assert output_suffix([], True) == "full_clean"

    def test_labels_are_sorted_not_left_in_input_order(self):
        assert output_suffix([49, 10], False) == "labels_10_49_raw"

    def test_labels_and_cleaning(self):
        assert output_suffix([10, 49], True) == "labels_10_49_clean"


class TestFindFieldNifti:
    def test_none_without_a_simulation_directory(self):
        assert find_field_nifti(None, "TI_max") is None
        assert find_field_nifti("/nowhere/at/all", "TI_max") is None

    def test_finds_the_subject_space_volume_recursively(self, tmp_path):
        niftis = tmp_path / "niftis"
        niftis.mkdir()
        (niftis / "sub-ernie_TI_subject_TI_max.nii.gz").write_bytes(b"")
        (niftis / "sub-ernie_TI_MNI_TI_max.nii.gz").write_bytes(b"")
        found = find_field_nifti(str(tmp_path), "TI_max")
        assert found is not None and os.path.basename(found).endswith("_subject_TI_max.nii.gz")

    def test_none_for_a_field_that_was_never_written(self, tmp_path):
        assert find_field_nifti(str(tmp_path), "TI_normal") is None


class TestJobWiring:
    def test_validate_resolves_the_type_to_the_dataclass(self):
        assert cls_for("blender", {"_type": "SubcorticalConfig"}) is SubcorticalConfig

    def test_blender_kind_runs_the_same_module_for_every_mode(self):
        cmd = command_for("blender", {"_type": "SubcorticalConfig"}, "/tmp/config.json")
        assert cmd == ["simnibs_python", "-m", "tit.blender", "/tmp/config.json"]

    def test_main_dispatch_knows_the_type(self):
        import tit.blender.__main__ as blender_main

        assert hasattr(blender_main, "_run_subcortical")
