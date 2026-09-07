"""Tests for tit.config_io.json_schema / deserialize_config, and for the two
schema-generation scripts that consume them (dev/build_schema.py,
dev/build_contract.py).

Covers, for every class in ``tit.config_io.CONFIG_CLASS_REGISTRY`` (the config
dataclasses the desktop contract is generated from):

- instance -> serialize_config -> validate against json_schema(cls) (draft
  2020-12, via the ``jsonschema`` package) -> deserialize_config ->
  equality with the original instance;
- discriminator (``"_type"``) presence exactly where serialize_config
  writes one, and its absence everywhere else (e.g. ExConfig.AtlasROI,
  which shares a bare name with the *discriminated* FlexConfig.AtlasROI
  but is never used polymorphically);
- the ``$defs`` renaming that keeps a merged, multi-class schema document
  collision-free (three AtlasROI, two PoolElectrodes, two BucketElectrodes,
  two Subject);
- deserialize_config rejecting an unknown/missing/mismatched ``_type``.

``jsonschema`` is not a project dependency; install it with
``python3 -m pip install --user --break-system-packages jsonschema`` if
these tests report it missing.
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# tit.stats.config's package __init__ eagerly imports tit.stats.permutation ->
# tit.stats.engine, which needs scipy.ndimage / scipy.stats. Neither is in
# tests/conftest.py's _MOCK_PACKAGES; test_plotting.py and test_pre_pipeline.py
# already carry this same local fallback so their (or this) module works
# regardless of pytest's file collection order.
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

jsonschema = pytest.importorskip(
    "jsonschema",
    reason=(
        "jsonschema is not a runtime dependency; install with "
        "`python3 -m pip install --user --break-system-packages jsonschema` "
        "to run these tests"
    ),
)

from tit.config_io import (  # noqa: E402
    CONFIG_CLASS_REGISTRY,
    deserialize_config,
    json_schema,
    resolve_config_class,
    serialize_config,
)
from tit.config_io import _deserialize_union  # noqa: E402
from tit.opt.config import ExConfig, FlexConfig, MExConfig  # noqa: E402
from tit.sim.config import Montage, SimulationConfig  # noqa: E402
from tit.analyzer.config import AnalyzerConfig  # noqa: E402
from tit.pre.config import (  # noqa: E402
    PreprocessConfig,
    QSIPrepSettings,
    QSIReconSettings,
)
from tit.pre.qsi.config import QSIPrepConfig, QSIReconConfig  # noqa: E402
from tit.stats.config import CorrelationConfig, GroupComparisonConfig  # noqa: E402
from tit.source.config import SourceConfig, SourcePair  # noqa: E402
from tit.opt.leadfield_config import LeadfieldConfig  # noqa: E402
from tit.blender.config import (  # noqa: E402
    MontageConfig,
    RegionConfig,
    SubcorticalConfig,
    VectorConfig,
)
from tit.stats.nifti_average_config import (  # noqa: E402
    NiftiAverageConfig,
    NiftiAverageSubject,
)
from tit.plotting.nilearn.config import (  # noqa: E402
    NilearnConfig,
    NilearnSubjectSimulation,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_dev_script(name: str):
    """Load ``dev/<name>.py`` as a module (mirrors test_server_skeleton.py's
    ``contracts_check`` loading pattern -- ``dev/`` is not a package)."""
    spec_path = REPO_ROOT / "dev" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, spec_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# One representative instance per registered class
# ---------------------------------------------------------------------------


def _sample_instances() -> dict[str, object]:
    """One instance per :data:`CONFIG_CLASS_REGISTRY` entry.

    Each instance exercises at least one optional field left at its
    dataclass default, so a default that fails its own generated schema
    (a real bug) would surface as a validation failure below, not just a
    round-trip mismatch.
    """
    return {
        "SimulationConfig": SimulationConfig(
            subject_id="ernie",
            montages=[
                Montage(
                    name="m1",
                    mode=Montage.Mode.NET,
                    electrode_pairs=[("E1", "E2"), ("E3", "E4")],
                    eeg_net="GSN-HydroCel-185.csv",
                    channels=[([0], [1])],
                )
            ],
            # Exercises the dict[int, float] round trip: JSON always has string keys
            # ({"1": 0.126, "3": 1.654}), and deserialize_config must coerce them back.
            tissue_conductivities={1: 0.126, 3: 1.654},
        ),
        "Montage": Montage(
            name="flex_free_1",
            mode=Montage.Mode.FLEX_FREE,
            electrode_pairs=[
                ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]),
                ([7.0, 8.0, 9.0], [10.0, 11.0, 12.0]),
            ],
        ),
        "FlexConfig": FlexConfig(
            subject_id="001",
            goal="focality_tf",
            postproc="max_TI",
            current_mA=2.0,
            electrode=FlexConfig.ElectrodeConfig(),
            roi=FlexConfig.AtlasROI(
                atlas_path="/atlas.annot", label=5, hemisphere="lh"
            ),
            non_roi=FlexConfig.SphericalROI(x=1.0, y=2.0, z=3.0),
        ),
        "ExConfig": ExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="target",
            electrodes=ExConfig.PoolElectrodes(electrodes=["C3", "C4", "Cz", "Pz"]),
        ),
        "MExConfig": MExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="target",
            electrodes=MExConfig.BucketElectrodes(
                e1_plus=["C3"],
                e1_minus=["C4"],
                e2_plus=["Cz"],
                e2_minus=["Pz"],
                e3_plus=["F3"],
                e3_minus=["F4"],
                e4_plus=["P3"],
                e4_minus=["P4"],
            ),
            channels=[([0, 2], [1, 3])],
        ),
        "AnalyzerConfig": AnalyzerConfig(
            mode="group",
            subject_ids=["001", "002"],
            simulation="sim1",
            analysis_type="cortical",
            atlas="DK40",
            region=["superiorfrontal", "precentral"],
        ),
        "PreprocessConfig": PreprocessConfig(
            subject_ids=["001", "002"],
            convert_dicom=True,
            run_qsiprep=True,
            qsiprep_config=QSIPrepSettings(cpus=8),
        ),
        "QSIPrepConfig": QSIPrepConfig(subject_id="001"),
        "QSIReconConfig": QSIReconConfig(subject_id="001", atlases=["AAL116"]),
        "QSIPrepSettings": QSIPrepSettings(cpus=8),
        "QSIReconSettings": QSIReconSettings(atlases=["AAL116"]),
        "GroupComparisonConfig": GroupComparisonConfig(
            analysis_name="responders_vs_non",
            subjects=[
                GroupComparisonConfig.Subject(
                    subject_id="1", simulation_name="sim1", response=1
                ),
                GroupComparisonConfig.Subject(
                    subject_id="2", simulation_name="sim1", response=0
                ),
            ],
        ),
        "CorrelationConfig": CorrelationConfig(
            analysis_name="effect_correlation",
            subjects=[
                CorrelationConfig.Subject(
                    subject_id="1", simulation_name="sim1", effect_size=1.0
                ),
                CorrelationConfig.Subject(
                    subject_id="2", simulation_name="sim1", effect_size=2.0, weight=0.5
                ),
                CorrelationConfig.Subject(
                    subject_id="3", simulation_name="sim1", effect_size=3.0
                ),
            ],
        ),
        "SourceConfig": SourceConfig(
            mode="fsavg_map",
            pairs=[SourcePair(subject_id="001", simulation="sim1")],
        ),
        "LeadfieldConfig": LeadfieldConfig(subject_id="001", tissues=[1, 2]),
        "MontageConfig": MontageConfig(subject_id="001", simulation_name="sim1"),
        "VectorConfig": VectorConfig(
            subject_id="001", simulation_name="sim1", export_sum=True
        ),
        "RegionConfig": RegionConfig(
            subject_id="001", simulation_name="sim1", field_range=(0.0, 1.0)
        ),
        "SubcorticalConfig": SubcorticalConfig(
            subject_id="001", simulation_name="sim1", labels=[10, 49]
        ),
        "NiftiAverageConfig": NiftiAverageConfig(
            output_name="responders_vs_non",
            subjects=[
                NiftiAverageSubject("001", "sim1", "Responders"),
                NiftiAverageSubject("002", "sim1", "NonResponders"),
            ],
            diff_pairs=["Responders-NonResponders"],
        ),
        "NilearnConfig": NilearnConfig(
            subject_simulation_pairs=[
                NilearnSubjectSimulation("001", "sim1"),
                NilearnSubjectSimulation("002", "sim1"),
            ],
            create_glass_brain=True,
        ),
    }


@pytest.fixture()
def sample_instances():
    return _sample_instances()


def test_sample_instances_cover_the_whole_registry(sample_instances):
    assert set(sample_instances) == set(CONFIG_CLASS_REGISTRY)


# ---------------------------------------------------------------------------
# instance -> serialize -> validate -> deserialize -> equality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRoundTrip:
    @pytest.mark.parametrize("name", sorted(CONFIG_CLASS_REGISTRY))
    def test_round_trip(self, name, sample_instances):
        cls = resolve_config_class(name)
        instance = sample_instances[name]
        assert type(instance) is cls

        schema = json_schema(cls)
        data = serialize_config(instance)
        data.pop("project_dir", None)

        jsonschema.Draft202012Validator(schema).validate(data)

        rebuilt = deserialize_config(cls, data)
        assert rebuilt == instance

    def test_schema_is_draft_2020_12_compatible(self, sample_instances):
        # Sanity check independent of the per-class loop: the validator
        # class itself must accept every generated schema as well-formed.
        for name in CONFIG_CLASS_REGISTRY:
            cls = resolve_config_class(name)
            jsonschema.Draft202012Validator.check_schema(json_schema(cls))


# ---------------------------------------------------------------------------
# Discriminator presence -- exactly where serialize_config tags a _type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiscriminatedUnions:
    def test_flex_roi_union_is_discriminated(self):
        schema = json_schema(FlexConfig)
        roi = schema["properties"]["roi"]
        assert "oneOf" in roi
        assert roi["discriminator"] == {"propertyName": "_type"}
        assert len(roi["oneOf"]) == 3

    def test_flex_non_roi_optional_union_keeps_null_branch(self):
        schema = json_schema(FlexConfig)
        non_roi = schema["properties"]["non_roi"]
        assert "oneOf" in non_roi
        assert {"type": "null"} in non_roi["oneOf"]
        assert non_roi["discriminator"] == {"propertyName": "_type"}

    @pytest.mark.parametrize("cls", [ExConfig, MExConfig])
    def test_electrodes_union_is_discriminated(self, cls):
        schema = json_schema(cls)
        electrodes = schema["properties"]["electrodes"]
        assert "oneOf" in electrodes
        assert electrodes["discriminator"] == {"propertyName": "_type"}
        assert len(electrodes["oneOf"]) == 2

    @pytest.mark.parametrize(
        "cls, discriminated_name",
        [
            (FlexConfig, "SphericalROI"),
            (FlexConfig.SubcorticalROI, "SubcorticalROI"),
        ],
    )
    def test_discriminated_members_carry_type_const(self, cls, discriminated_name):
        schema = json_schema(cls if cls is FlexConfig else FlexConfig)
        target = schema["$defs"][discriminated_name]
        assert target["properties"]["_type"] == {"const": discriminated_name}
        assert "_type" in target["required"]

    @pytest.mark.parametrize(
        "cls, defs_name",
        [
            (ExConfig, "ExConfigAtlasROI"),
            (MExConfig, "MExConfigAtlasROI"),
        ],
    )
    def test_non_polymorphic_atlas_roi_has_no_type_const(self, cls, defs_name):
        """ExConfig.AtlasROI / MExConfig.AtlasROI share a bare name with the
        *discriminated* FlexConfig.AtlasROI, but each is only ever used in a
        plain ``list[AtlasROI]`` field -- serialize_config never tags an
        instance of either with ``_type``, so their schema must not require
        one (a schema that did would reject exactly what
        serialize_config produces)."""
        schema = json_schema(cls)
        target = schema["$defs"][defs_name]
        assert "_type" not in target.get("properties", {})
        assert "_type" not in target.get("required", [])


# ---------------------------------------------------------------------------
# $defs collision-safe renaming
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefsCollisionRenaming:
    @pytest.mark.parametrize(
        "cls, expected_defs_name",
        [
            (FlexConfig, "FlexConfigAtlasROI"),
            (ExConfig, "ExConfigAtlasROI"),
            (MExConfig, "MExConfigAtlasROI"),
        ],
    )
    def test_three_atlas_roi_get_distinct_names(self, cls, expected_defs_name):
        schema = json_schema(cls)
        assert expected_defs_name in schema["$defs"]
        assert "AtlasROI" not in schema["$defs"]

    @pytest.mark.parametrize(
        "cls, expected_pool, expected_bucket",
        [
            (ExConfig, "ExConfigPoolElectrodes", "ExConfigBucketElectrodes"),
            (MExConfig, "MExConfigPoolElectrodes", "MExConfigBucketElectrodes"),
        ],
    )
    def test_pool_and_bucket_electrodes_get_distinct_names(
        self, cls, expected_pool, expected_bucket
    ):
        schema = json_schema(cls)
        assert expected_pool in schema["$defs"]
        assert expected_bucket in schema["$defs"]
        assert "PoolElectrodes" not in schema["$defs"]
        assert "BucketElectrodes" not in schema["$defs"]

    @pytest.mark.parametrize(
        "cls, expected_defs_name",
        [
            (GroupComparisonConfig, "GroupComparisonConfigSubject"),
            (CorrelationConfig, "CorrelationConfigSubject"),
        ],
    )
    def test_subject_gets_distinct_name(self, cls, expected_defs_name):
        schema = json_schema(cls)
        assert expected_defs_name in schema["$defs"]
        assert "Subject" not in schema["$defs"]

    def test_refs_are_rewritten_to_match_the_rename(self):
        schema = json_schema(FlexConfig)
        dumped = json.dumps(schema)
        assert '"#/$defs/AtlasROI"' not in dumped
        assert '"#/$defs/FlexConfigAtlasROI"' in dumped

    def test_merging_all_16_classes_never_collides(self, sample_instances):
        """The same collision-safety dev/build_schema.py relies on, exercised
        directly: union-merging every registered class's own $defs must
        never let two different classes' bodies collide under one key."""
        combined: dict[str, dict] = {}
        for name in sorted(CONFIG_CLASS_REGISTRY):
            cls = resolve_config_class(name)
            schema = json_schema(cls)
            nested = schema.pop("$defs", {})
            combined[name] = schema
            for def_name, def_schema in nested.items():
                if def_name in combined:
                    assert (
                        combined[def_name] == def_schema
                    ), f"$defs collision on {def_name!r} while merging {name!r}"
                combined[def_name] = def_schema
        # Sanity: every renamed name landed, no bare colliding name survived.
        for bare in ("AtlasROI", "PoolElectrodes", "BucketElectrodes", "Subject"):
            assert bare not in combined


# ---------------------------------------------------------------------------
# deserialize_config rejects bad _type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeserializeRejectsUnknownType:
    def test_top_level_type_mismatch_raises(self):
        data = serialize_config(
            ExConfig.PoolElectrodes(electrodes=["C3", "C4", "Cz", "Pz"])
        )
        data["_type"] = "BucketElectrodes"
        with pytest.raises(ValueError, match="does not match"):
            deserialize_config(ExConfig.PoolElectrodes, data)

    def test_union_missing_type_raises(self):
        with pytest.raises(ValueError, match="Missing or unknown"):
            _deserialize_union(
                {"electrodes": ["C3"]},
                [ExConfig.PoolElectrodes, ExConfig.BucketElectrodes],
            )

    def test_union_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Missing or unknown"):
            _deserialize_union(
                {"_type": "NotARealType"},
                [ExConfig.PoolElectrodes, ExConfig.BucketElectrodes],
            )

    def test_flex_roi_unknown_type_raises_end_to_end(self):
        data = serialize_config(
            FlexConfig(
                subject_id="001",
                goal="mean",
                postproc="max_TI",
                current_mA=1.0,
                electrode=FlexConfig.ElectrodeConfig(),
                roi=FlexConfig.SphericalROI(x=0, y=0, z=0),
            )
        )
        data.pop("project_dir", None)
        data["roi"]["_type"] = "NotAnROI"
        with pytest.raises(ValueError, match="Missing or unknown"):
            deserialize_config(FlexConfig, data)


# ---------------------------------------------------------------------------
# deserialize_config(strict=True) / json_schema's additionalProperties: false
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStrictDeserialize:
    """ra_11 finding 3: a misspelled/renamed key must not silently vanish."""

    def _flex_data(self, **extra):
        data = serialize_config(
            FlexConfig(
                subject_id="001",
                goal="mean",
                postproc="max_TI",
                current_mA=1.0,
                electrode=FlexConfig.ElectrodeConfig(),
                roi=FlexConfig.SphericalROI(x=0, y=0, z=0),
            )
        )
        data.pop("project_dir", None)
        data.update(extra)
        return data

    def test_default_is_lenient_like_before(self):
        data = self._flex_data(totally_bogus_field=123)
        config = deserialize_config(FlexConfig, data)
        assert config.subject_id == "001"
        assert not hasattr(config, "totally_bogus_field")

    def test_strict_rejects_unknown_top_level_key(self):
        data = self._flex_data(totally_bogus_field=123)
        with pytest.raises(ValueError, match="totally_bogus_field"):
            deserialize_config(FlexConfig, data, strict=True)

    def test_strict_accepts_a_clean_payload(self):
        data = self._flex_data()
        config = deserialize_config(FlexConfig, data, strict=True)
        assert config.subject_id == "001"

    def test_strict_message_names_the_class(self):
        data = self._flex_data(bogus=1)
        with pytest.raises(ValueError, match="FlexConfig"):
            deserialize_config(FlexConfig, data, strict=True)

    def test_strict_ignores_type_discriminator(self):
        """`_type` is not a real field of any class, but is never flagged."""
        data = serialize_config(
            ExConfig.PoolElectrodes(electrodes=["C3", "C4", "Cz", "Pz"])
        )
        data.pop("project_dir", None)
        assert data["_type"] == "PoolElectrodes"
        deserialize_config(ExConfig.PoolElectrodes, data, strict=True)

    def test_strict_propagates_into_nested_dataclasses(self):
        """A misspelling inside a nested object (not just the top level) is caught too."""
        data = self._flex_data()
        data["electrode"]["bogus_nested_key"] = 1
        with pytest.raises(ValueError, match="bogus_nested_key"):
            deserialize_config(FlexConfig, data, strict=True)

    def test_strict_propagates_through_discriminated_unions(self):
        data = self._flex_data()
        data["roi"]["bogus_roi_key"] = 1
        with pytest.raises(ValueError, match="bogus_roi_key"):
            deserialize_config(FlexConfig, data, strict=True)

    def test_new_flex_driver_fields_round_trip_under_strict_mode(self):
        """FlexConfig.mode/adaptive/pareto are real fields, not incidental extras."""
        config = FlexConfig(
            subject_id="001",
            goal="focality",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexConfig.ElectrodeConfig(),
            roi=FlexConfig.SphericalROI(x=0, y=0, z=0),
            mode="flex_pareto",
        )
        data = serialize_config(config)
        data.pop("project_dir", None)
        rebuilt = deserialize_config(FlexConfig, data, strict=True)
        assert rebuilt.mode is FlexConfig.Mode.FLEX_PARETO
        assert rebuilt.pareto == FlexConfig.ParetoSweepConfig()


@pytest.mark.unit
class TestAdditionalPropertiesFalse:
    """json_schema(cls) closes every fixed-shape object schema."""

    @pytest.mark.parametrize("name", sorted(CONFIG_CLASS_REGISTRY))
    def test_top_level_and_every_def_is_closed(self, name):
        cls = resolve_config_class(name)
        schema = json_schema(cls)
        assert schema.get("additionalProperties") is False
        for def_name, defn in schema.get("$defs", {}).items():
            if "properties" in defn:
                assert defn.get("additionalProperties") is False, def_name

    def test_free_form_dict_field_is_left_open(self):
        """SimulationConfig.tissue_conductivities: dict[int, float] has no fixed
        `properties`, so it must stay open rather than becoming additionalProperties: false.
        """
        from tit.sim.config import SimulationConfig

        schema = json_schema(SimulationConfig)
        # anyOf[dict-schema, null] for the Optional[dict[int, float]] field.
        prop = schema["properties"]["tissue_conductivities"]
        branches = prop.get("anyOf", [prop])
        dict_branch = next(b for b in branches if b.get("type") == "object")
        assert "properties" not in dict_branch
        assert dict_branch.get("additionalProperties") != False  # noqa: E712

    def test_jsonschema_rejects_a_misspelled_key(self):
        """The same misspelling deserialize_config(strict=True) rejects also fails
        schema validation -- the two enforcement points agree."""
        schema = json_schema(FlexConfig)
        data = serialize_config(
            FlexConfig(
                subject_id="001",
                goal="mean",
                postproc="max_TI",
                current_mA=1.0,
                electrode=FlexConfig.ElectrodeConfig(),
                roi=FlexConfig.SphericalROI(x=0, y=0, z=0),
            )
        )
        data.pop("project_dir", None)
        data["totally_bogus_field"] = 1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(data)


# ---------------------------------------------------------------------------
# dev/build_schema.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildSchemaScript:
    def test_build_schema_covers_the_registry(self):
        build_schema = _load_dev_script("build_schema")
        doc = build_schema.build_schema()
        assert set(doc["x-tit-classes"]) == set(CONFIG_CLASS_REGISTRY)
        assert doc["x-tit-classes"] == CONFIG_CLASS_REGISTRY
        for name in CONFIG_CLASS_REGISTRY:
            assert name in doc["$defs"]
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_build_schema_is_idempotent(self):
        build_schema = _load_dev_script("build_schema")
        first = build_schema.render(build_schema.build_schema())
        second = build_schema.render(build_schema.build_schema())
        assert first == second

    def test_collision_names_absent_from_combined_document(self):
        build_schema = _load_dev_script("build_schema")
        doc = build_schema.build_schema()
        for bare in ("AtlasROI", "PoolElectrodes", "BucketElectrodes", "Subject"):
            assert bare not in doc["$defs"]


# ---------------------------------------------------------------------------
# dev/build_contract.py -- exercised against a tiny synthetic contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildContractScript:
    @pytest.fixture()
    def build_contract(self):
        return _load_dev_script("build_contract")

    @pytest.fixture()
    def tiny_schema_doc(self):
        return {
            "$defs": {
                "Widget": {
                    "type": "object",
                    "properties": {
                        "size": {"$ref": "#/$defs/Size"},
                    },
                    "required": ["size"],
                },
                "Size": {"type": "integer"},
                "Unused": {"type": "string"},
            }
        }

    @pytest.fixture()
    def tiny_openapi(self):
        return {
            "openapi": "3.1.0",
            "info": {"title": "tiny", "version": "0"},
            "paths": {},
            "components": {
                "schemas": {
                    "WidgetBody": {"x-tit-config": "Widget"},
                    "Unrelated": {"type": "object", "properties": {}},
                }
            },
        }

    def test_merge_replaces_marked_schema_and_copies_transitive_refs(
        self, build_contract, tiny_openapi, tiny_schema_doc
    ):
        merged = build_contract.merge(copy.deepcopy(tiny_openapi), tiny_schema_doc)
        schemas = merged["components"]["schemas"]

        assert schemas["WidgetBody"]["required"] == ["size"]
        assert schemas["WidgetBody"]["properties"]["size"] == {
            "$ref": "#/components/schemas/Size"
        }
        # transitively-referenced $defs entry copied in under its own name
        assert schemas["Size"] == {"type": "integer"}
        # a $defs entry nothing references is left uncopied
        assert "Unused" not in schemas
        # an already-present, unmarked schema is untouched
        assert schemas["Unrelated"] == {"type": "object", "properties": {}}
        # no internal $defs refs survive the merge
        assert "#/$defs/" not in json.dumps(merged)

    def test_merge_is_a_no_op_without_any_marker(self, build_contract, tiny_schema_doc):
        openapi = {"components": {"schemas": {"Plain": {"type": "string"}}}}
        merged = build_contract.merge(copy.deepcopy(openapi), tiny_schema_doc)
        assert merged == openapi

    def test_merge_raises_a_clear_error_for_an_unknown_defs_name(
        self, build_contract, tiny_schema_doc
    ):
        openapi = {"components": {"schemas": {"Bad": {"x-tit-config": "NoSuchDefs"}}}}
        with pytest.raises(KeyError, match="NoSuchDefs"):
            build_contract.merge(openapi, tiny_schema_doc)

    def test_main_reports_a_clear_error_when_openapi_is_missing(
        self, build_contract, tmp_path, capsys
    ):
        missing = tmp_path / "does-not-exist.yaml"
        rc = build_contract.main(["--openapi", str(missing)])
        assert rc == 1
        assert "does not exist yet" in capsys.readouterr().err

    def test_main_reports_a_clear_error_when_schema_is_missing(
        self, build_contract, tmp_path, capsys
    ):
        openapi_path = tmp_path / "openapi.v1.yaml"
        openapi_path.write_text("openapi: 3.1.0\ncomponents:\n  schemas: {}\n")
        missing_schema = tmp_path / "schema.json"
        rc = build_contract.main(
            ["--openapi", str(openapi_path), "--schema", str(missing_schema)]
        )
        assert rc == 1
        assert "does not exist yet" in capsys.readouterr().err

    def test_main_writes_a_json_sibling_end_to_end(
        self, build_contract, tmp_path, tiny_openapi, tiny_schema_doc
    ):
        import yaml

        openapi_path = tmp_path / "openapi.v1.yaml"
        openapi_path.write_text(yaml.safe_dump(tiny_openapi))
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps(tiny_schema_doc))

        rc = build_contract.main(
            ["--openapi", str(openapi_path), "--schema", str(schema_path)]
        )
        assert rc == 0
        out_path = openapi_path.with_suffix(".json")
        assert out_path.is_file()
        written = json.loads(out_path.read_text())
        assert written["components"]["schemas"]["Size"] == {"type": "integer"}
