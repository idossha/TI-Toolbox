"""Unit tests for the sub-cortical export mode of the ``blender`` job kind.

2.5.0 ran this mode inline on the Qt main thread, so it had no config dataclass, no runner module
and no test. This file covers the three things the migration to a job depends on:

- :class:`tit.blender.config.SubcorticalConfig` validating and round-tripping like every other
  registered config (the wider registry sweep lives in ``tests/test_config_schema.py``);
- the filename rule (``labels_10_49_clean`` / ``full_raw``), which keeps the geometry files'
  names 2.5.0's, and the field-NIfTI lookup: the unmasked subject-space volume
  (``TI/niftis/<sim>_TI_subject_<field>`` or the mTI one), named by Dataset 000's real files;
- the wiring itself -- ``kind="blender"`` with ``_type="SubcorticalConfig"`` reaching
  ``tit.blender.__main__``'s dispatch, and ``routes/validate.py`` resolving it to the right class.
"""

import os

import pytest

from tit.blender.config import SubcorticalConfig
from tit.blender.subcortical_exporter import field_nifti_path, output_suffix
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
        assert SubcorticalConfig(subject_id="ernie", labels=["10", 49]).labels == [
            10,
            49,
        ]

    def test_non_integer_label_raises(self):
        with pytest.raises(ValueError, match="labels must be integers"):
            SubcorticalConfig(subject_id="ernie", labels=["thalamus"])

    def test_round_trips_with_its_discriminator(self):
        cfg = SubcorticalConfig(
            subject_id="ernie", simulation_name="sim1", labels=[10, 49]
        )
        data = serialize_config(cfg)
        assert (
            data["_type"]
            == "SubcorticalConfig"
            == _discriminator_for(SubcorticalConfig)
        )
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


#: The ``TI/niftis`` names Dataset 000 holds for two TI runs (listed from disk 2026-10-22): the
#: whole-head volume, plus the grey- and white-matter masked copies ``mesh2nii`` also writes.
#: Sorting them put ``grey_*`` first for a lower-case simulation name and the whole-head file
#: first for an upper-case one, so the colour source depended on how the run was named.
_DATASET_000_NIFTIS = {
    ("CHN", "left_insula_mean"): [
        "grey_left_insula_mean_TI_subject_TI_max.nii.gz",
        "left_insula_mean_TI_subject_TI_max.nii.gz",
        "white_left_insula_mean_TI_subject_TI_max.nii.gz",
    ],
    ("101", "L_Insula"): [
        "grey_L_Insula_TI_MNI_MNI_TI_max.nii.gz",
        "grey_L_Insula_TI_subject_TI_max.nii.gz",
        "L_Insula_TI_MNI_MNI_TI_max.nii.gz",
        "L_Insula_TI_subject_TI_max.nii.gz",
        "white_L_Insula_TI_subject_TI_max.nii.gz",
    ],
}


def _sim(project, sid, sim):
    return project / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / sim


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


class TestFieldNiftiPath:
    """The field volume that colours the PLY: the unmasked subject-space one, TI or mTI."""

    @pytest.mark.parametrize("sid, sim", sorted(_DATASET_000_NIFTIS))
    def test_ti_run_is_coloured_from_the_whole_head_volume(self, tmp_path, sid, sim):
        from tit.paths import get_path_manager

        get_path_manager(str(tmp_path))
        niftis = _sim(tmp_path, sid, sim) / "TI" / "niftis"
        for name in _DATASET_000_NIFTIS[(sid, sim)]:
            _touch(niftis / name)
        _touch(
            _sim(tmp_path, sid, sim)
            / "high_Frequency"
            / "niftis"
            / f"{sid}_TDCS_1_scalar_subject_magnE.nii.gz"
        )
        # mesh2nii names the whole mesh <sim>_TI_subject_<field> (no tissue prefix).
        assert field_nifti_path(sid, sim, "TI_max") == str(
            niftis / f"{sim}_TI_subject_TI_max.nii.gz"
        )

    def test_mti_run_is_coloured_from_its_mti_max_volume(self, tmp_path):
        from tit.paths import get_path_manager

        get_path_manager(str(tmp_path))
        sim = _sim(tmp_path, "001", "Deep")
        (sim / "mTI" / "mesh").mkdir(parents=True)
        # The field the user typed is the 2-pair name; an mTI run spells it mTI_max.
        assert field_nifti_path("001", "Deep", "TI_max") == str(
            sim / "mTI" / "niftis" / "Deep_mTI_subject_mTI_max.nii.gz"
        )
        assert field_nifti_path("001", "Deep", "hf_peak") == str(
            sim / "mTI" / "niftis" / "Deep_mTI_subject_hf_peak.nii.gz"
        )


class TestRunnerFieldPly:
    """``run_subcortical`` colours from that volume, and names it when it is missing."""

    @pytest.fixture
    def run(self, tmp_path, monkeypatch):
        import logging

        from tit.paths import get_path_manager
        from tit.blender.subcortical_exporter import run_subcortical
        import tit.tools.nifti_to_mesh as n2m

        get_path_manager(str(tmp_path))
        labeling = _touch(tmp_path / "labeling.nii.gz")
        calls = []

        def mesh(input_file, output_file, **kwargs):
            return {
                "output_file": output_file,
                "vertices": 3,
                "faces": 1,
                "removed_components": 0,
            }

        def ply(mask_file, field_file, output_file, **kwargs):
            calls.append((field_file, kwargs["field_name"]))
            return {
                "output_file": output_file,
                "vertices": 3,
                "faces": 1,
                "field_min": 0.0,
                "field_max": 1.0,
            }

        monkeypatch.setattr(n2m, "nifti_to_mesh", mesh)
        monkeypatch.setattr(n2m, "nifti_to_field_ply", ply)

        class Lines(logging.Handler):
            def __init__(self):
                super().__init__()
                self.lines = []

            def emit(self, record):
                self.lines.append((record.levelname, record.getMessage()))

        log = logging.getLogger("test_blender_subcortical.run")
        handler = Lines()
        log.addHandler(handler)

        def go(sim_name, field="TI_max"):
            cfg = SubcorticalConfig(
                subject_id="001",
                simulation_name=sim_name,
                nifti_path=str(labeling),
                field_name=field,
            )
            run_subcortical(cfg, logger_override=log)
            return calls, handler.lines

        yield go
        log.removeHandler(handler)

    def test_mti_ply_is_coloured_from_the_mti_volume(self, run, tmp_path):
        sim = _sim(tmp_path, "001", "Deep")
        (sim / "mTI" / "mesh").mkdir(parents=True)
        volume = _touch(sim / "mTI" / "niftis" / "Deep_mTI_subject_mTI_max.nii.gz")
        _touch(sim / "TI" / "niftis" / "Deep_TI_AB_subject_TI_max.nii.gz")
        calls, _ = run("Deep")
        assert calls == [(str(volume), "mTI_max")]

    def test_a_missing_volume_is_named_in_the_warning(self, run, tmp_path):
        sim = _sim(tmp_path, "001", "L_Insula")
        _touch(sim / "TI" / "niftis" / "grey_L_Insula_TI_subject_TI_max.nii.gz")
        calls, lines = run("L_Insula")
        assert calls == []  # never coloured from the grey-matter-masked copy
        expected = str(sim / "TI" / "niftis" / "L_Insula_TI_subject_TI_max.nii.gz")
        assert any(level == "WARNING" and expected in msg for level, msg in lines)


@pytest.mark.skipif(
    not os.path.isdir(os.environ.get("TIT_DATASET_000", "") or "/nonexistent"),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
@pytest.mark.parametrize("sid, sim", sorted(_DATASET_000_NIFTIS))
def test_dataset_000_runs_resolve_to_their_whole_head_volume(sid, sim):
    """On the real runs the resolved file exists and is not a tissue-masked copy."""
    from tit.paths import get_path_manager

    root = os.environ["TIT_DATASET_000"]
    get_path_manager(root)
    path = field_nifti_path(sid, sim, "TI_max")
    before = os.stat(path).st_mtime_ns
    assert os.path.isfile(path)
    assert not os.path.basename(path).startswith(("grey_", "white_"))
    assert os.path.basename(path) == f"{sim}_TI_subject_TI_max.nii.gz"
    assert os.stat(path).st_mtime_ns == before  # read-only: nothing touched the dataset


class TestJobWiring:
    def test_validate_resolves_the_type_to_the_dataclass(self):
        assert cls_for("blender", {"_type": "SubcorticalConfig"}) is SubcorticalConfig

    def test_blender_kind_runs_the_same_module_for_every_mode(self):
        cmd = command_for("blender", {"_type": "SubcorticalConfig"}, "/tmp/config.json")
        assert cmd == ["simnibs_python", "-m", "tit.blender", "/tmp/config.json"]

    def test_main_dispatch_knows_the_type(self):
        import tit.blender.__main__ as blender_main

        assert hasattr(blender_main, "_run_subcortical")
