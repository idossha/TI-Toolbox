"""Integration tests for the tit.blender package.

Covers:
- Config serialization round-trips via tit.config_io
- __main__.py dispatch (correct function called per _type)
- __init__.py public API exports
"""

import json
import sys
from unittest.mock import patch

import pytest

from tit.blender.config import (
    MontageConfig,
    RegionConfig,
    VectorConfig,
)
from tit.config_io import serialize_config

# ---------------------------------------------------------------------------
# Config serialization
# ---------------------------------------------------------------------------


class TestMontageConfigSerialization:
    """serialize_config for MontageConfig."""

    def test_has_type_discriminator(self):
        cfg = MontageConfig(
            subject_id="001",
            simulation_name="sim_A",
        )
        data = serialize_config(cfg)
        assert data["_type"] == "MontageConfig"

    def test_fields_serialized(self):
        cfg = MontageConfig(
            subject_id="001",
            simulation_name="sim_A",
            output_dir="/out",
            show_full_net=False,
            electrode_diameter_mm=12.0,
            electrode_height_mm=8.0,
        )
        data = serialize_config(cfg)
        assert data["subject_id"] == "001"
        assert data["simulation_name"] == "sim_A"
        assert data["output_dir"] == "/out"
        assert data["show_full_net"] is False
        assert data["electrode_diameter_mm"] == 12.0
        assert data["electrode_height_mm"] == 8.0

    def test_none_values_preserved(self):
        cfg = MontageConfig(
            subject_id="001",
            simulation_name="sim_A",
        )
        data = serialize_config(cfg)
        assert data["output_dir"] is None


class TestVectorConfigSerialization:
    """serialize_config for VectorConfig."""

    def test_has_type_discriminator(self):
        cfg = VectorConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
        )
        data = serialize_config(cfg)
        assert data["_type"] == "VectorConfig"

    def test_required_fields_serialized(self):
        cfg = VectorConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
        )
        data = serialize_config(cfg)
        assert data["subject_id"] == "ernie"
        assert data["simulation_name"] == "L_Insula"

    def test_enum_values_serialized_as_strings(self):
        cfg = VectorConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
            color=VectorConfig.Color.MAGSCALE,
            length_mode=VectorConfig.Length.VISUAL,
            anchor=VectorConfig.Anchor.HEAD,
        )
        data = serialize_config(cfg)
        assert data["color"] == "magscale"
        assert data["length_mode"] == "visual"
        assert data["anchor"] == "head"

    def test_none_optional_fields(self):
        cfg = VectorConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
        )
        data = serialize_config(cfg)
        assert data["mesh3"] is None
        assert data["mesh4"] is None
        assert data["top_percent"] is None


class TestRegionConfigSerialization:
    """serialize_config for RegionConfig."""

    def test_has_type_discriminator(self):
        cfg = RegionConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
        )
        data = serialize_config(cfg)
        assert data["_type"] == "RegionConfig"

    def test_enum_values_serialized(self):
        cfg = RegionConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
            format=RegionConfig.Format.STL,
            surface=RegionConfig.Surface.PIAL,
        )
        data = serialize_config(cfg)
        assert data["format"] == "stl"
        assert data["surface"] == "pial"

    def test_list_fields_serialized(self):
        cfg = RegionConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
            regions=["lh.precentral", "rh.postcentral"],
        )
        data = serialize_config(cfg)
        assert data["regions"] == ["lh.precentral", "rh.postcentral"]

    def test_tuple_field_range_serialized_as_list(self):
        cfg = RegionConfig(
            subject_id="ernie",
            simulation_name="L_Insula",
            field_range=(0.0, 5.0),
        )
        data = serialize_config(cfg)
        # Tuples become lists in JSON serialization
        assert data["field_range"] == [0.0, 5.0]


# ---------------------------------------------------------------------------
# __main__.py dispatch
# ---------------------------------------------------------------------------


class TestMainDispatch:
    """__main__.main() dispatches based on _type discriminator."""

    def test_montage_dispatch(self, tmp_path):
        config_data = {
            "_type": "MontageConfig",
            "project_dir": str(tmp_path),
            "subject_id": "001",
            "simulation_name": "sim_A",
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.blender.__main__.main.__module__", "tit.blender.__main__"),
            patch("tit.blender.montage_publication.run_montage") as mock_run,
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cfg = call_args[0][0]
        assert isinstance(cfg, MontageConfig)
        assert cfg.subject_id == "001"

    def test_vector_dispatch(self, tmp_path):
        config_data = {
            "_type": "VectorConfig",
            "project_dir": str(tmp_path),
            "subject_id": "ernie",
            "simulation_name": "L_Insula",
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.blender.vector_field_exporter.run_vectors") as mock_run,
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 0
        mock_run.assert_called_once()
        cfg = mock_run.call_args[0][0]
        assert isinstance(cfg, VectorConfig)
        assert cfg.subject_id == "ernie"

    def test_region_dispatch(self, tmp_path):
        config_data = {
            "_type": "RegionConfig",
            "project_dir": str(tmp_path),
            "subject_id": "ernie",
            "simulation_name": "L_Insula",
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.blender.region_exporter.run_regions") as mock_run,
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 0
        mock_run.assert_called_once()
        cfg = mock_run.call_args[0][0]
        assert isinstance(cfg, RegionConfig)
        assert cfg.subject_id == "ernie"

    def test_region_coerces_field_range(self, tmp_path):
        config_data = {
            "_type": "RegionConfig",
            "project_dir": str(tmp_path),
            "subject_id": "ernie",
            "simulation_name": "L_Insula",
            "field_range": [0.0, 5.0],
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.blender.region_exporter.run_regions") as mock_run,
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 0
        cfg = mock_run.call_args[0][0]
        assert cfg.field_range == (0.0, 5.0)

    def test_unknown_fields_in_json_are_ignored(self, tmp_path):
        """Old JSON with path fields still works (fields are filtered out)."""
        config_data = {
            "_type": "VectorConfig",
            "project_dir": str(tmp_path),
            "subject_id": "ernie",
            "simulation_name": "L_Insula",
            "gm_mesh": "/old/path.msh",
            "global_from_nifti": "/old/nifti.nii.gz",
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.blender.vector_field_exporter.run_vectors") as mock_run,
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 0
        mock_run.assert_called_once()

    def test_unknown_type_returns_error(self, tmp_path):
        config_data = {"_type": "UnknownConfig", "project_dir": str(tmp_path), "foo": "bar"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 1

    def test_missing_type_returns_error(self, tmp_path):
        config_data = {"project_dir": str(tmp_path), "foo": "bar"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with (
            patch.object(sys, "argv", ["blender", str(config_file)]),
            patch("tit.paths.get_path_manager"),
        ):
            from tit.blender.__main__ import main

            result = main()

        assert result == 1

    def test_no_args_returns_error(self):
        with patch.object(sys, "argv", ["blender"]):
            from tit.blender.__main__ import main

            result = main()

        assert result == 1


# ---------------------------------------------------------------------------
# __init__.py public API exports
# ---------------------------------------------------------------------------


class TestBlenderExports:
    """All expected names are importable from tit.blender."""

    @pytest.mark.parametrize(
        "name",
        [
            "MontageConfig",
            "VectorConfig",
            "RegionConfig",
            "run_montage",
            "MontageResult",
            "run_vectors",
            "run_regions",
        ],
    )
    def test_export_exists(self, name):
        import tit.blender

        assert hasattr(tit.blender, name), f"{name} not found in tit.blender"

    def test_all_list_matches_exports(self):
        import tit.blender

        expected = {
            "MontageConfig",
            "VectorConfig",
            "RegionConfig",
            "run_montage",
            "MontageResult",
            "run_vectors",
            "run_regions",
        }
        assert set(tit.blender.__all__) == expected
