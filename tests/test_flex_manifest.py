"""Tests for flex-search manifest and output naming."""

import json
import os
import re

import pytest

from tit.opt.config import FlexConfig, FlexResult

# Convenience aliases for nested types
SphericalROI = FlexConfig.SphericalROI
AtlasROI = FlexConfig.AtlasROI
SubcorticalROI = FlexConfig.SubcorticalROI
FlexElectrodeConfig = FlexConfig.ElectrodeConfig
from tit.opt.flex.manifest import (
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    write_manifest,
    read_manifest,
    _serialize_roi,
)
from tit.opt.flex.utils import (
    generate_run_dirname,
    generate_label,
    parse_optimization_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(roi, goal="mean", postproc="max_TI", **kwargs):
    return FlexConfig(
        subject_id="001",
        goal=goal,
        postproc=postproc,
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=roi,
        **kwargs,
    )


def _make_result(success=True, values=None):
    values = values or [-0.025]
    return FlexResult(
        success=success,
        output_folder="/tmp/out",
        function_values=values,
        best_value=min(values),
        best_run_index=values.index(min(values)),
    )


# ---------------------------------------------------------------------------
# _serialize_roi
# ---------------------------------------------------------------------------


class TestSerializeROI:
    def test_serialize_roi_spherical(self):
        roi = SphericalROI(x=-42.0, y=-20.0, z=55.0, radius=10.0, use_mni=True)
        d = _serialize_roi(roi)
        assert d["type"] == "spherical"
        assert d["x"] == -42.0
        assert d["y"] == -20.0
        assert d["z"] == 55.0
        assert d["radius"] == 10.0
        assert d["use_mni"] is True

    def test_serialize_roi_atlas(self):
        roi = AtlasROI(
            atlas_path="/path/to/lh.aparc.annot", label=1001, hemisphere="lh"
        )
        d = _serialize_roi(roi)
        assert d["type"] == "atlas"
        assert d["atlas_path"] == "/path/to/lh.aparc.annot"
        assert d["label"] == 1001
        assert d["hemisphere"] == "lh"

    def test_serialize_roi_subcortical(self):
        roi = SubcorticalROI(atlas_path="/path/to/aseg.nii.gz", label=11, tissues="GM")
        d = _serialize_roi(roi)
        assert d["type"] == "subcortical"
        assert d["atlas_path"] == "/path/to/aseg.nii.gz"
        assert d["label"] == 11
        assert d["tissues"] == "GM"


# ---------------------------------------------------------------------------
# write_manifest / read_manifest
# ---------------------------------------------------------------------------


class TestManifestIO:
    def test_write_read_manifest_roundtrip(self, tmp_path):
        roi = SphericalROI(x=-42.0, y=-20.0, z=55.0, radius=10.0, use_mni=True)
        config = _make_config(roi, n_multistart=3)
        result = _make_result(values=[-0.045, -0.042, -0.049])
        label = "mean_maxTI_sphere(-42,-20,55)r10"

        path = write_manifest(str(tmp_path), config, result, label)
        assert os.path.isfile(path)
        assert path.endswith(MANIFEST_FILENAME)

        data = read_manifest(str(tmp_path))
        assert data is not None
        assert data["version"] == MANIFEST_VERSION
        assert data["subject_id"] == "001"
        assert data["goal"] == "mean"
        assert data["postproc"] == "max_TI"
        assert data["current_mA"] == 2.0
        assert data["electrode"]["shape"] == "ellipse"
        assert data["electrode"]["dimensions"] == [8.0, 8.0]
        assert data["electrode"]["gel_thickness"] == 4.0
        assert data["roi"]["type"] == "spherical"
        assert data["roi"]["x"] == -42.0
        assert data["non_roi"] is None
        assert data["non_roi_method"] is None
        assert data["thresholds"] is None
        assert data["n_multistart"] == 3
        assert data["result"]["success"] is True
        assert data["result"]["best_value"] == -0.049
        assert data["result"]["best_run_index"] == 2
        assert data["result"]["all_values"] == [-0.045, -0.042, -0.049]
        assert data["pareto"] is None
        assert data["label"] == label

    def test_read_manifest_missing_file(self, tmp_path):
        result = read_manifest(str(tmp_path / "nonexistent"))
        assert result is None

    def test_read_manifest_corrupt_json(self, tmp_path):
        bad_file = tmp_path / MANIFEST_FILENAME
        bad_file.write_text("{invalid json content!!")
        result = read_manifest(str(tmp_path))
        assert result is None

    def test_manifest_multistart_scores(self, tmp_path):
        roi = SphericalROI(x=0, y=0, z=0, radius=5.0)
        config = _make_config(roi, n_multistart=5)
        values = [-0.010, -0.020, -0.015, -0.030, -0.025]
        result = _make_result(values=values)

        write_manifest(str(tmp_path), config, result, "test_label")
        data = read_manifest(str(tmp_path))

        assert data["n_multistart"] == 5
        assert data["result"]["all_values"] == values
        assert data["result"]["best_value"] == min(values)
        assert data["result"]["best_run_index"] == 3

    def test_manifest_with_pareto_data(self, tmp_path):
        roi = SphericalROI(x=-42.0, y=-20.0, z=55.0, radius=10.0)
        config = _make_config(roi, goal="focality")
        result = _make_result(values=[-0.0042])
        pareto_data = {
            "roi_pcts": [80.0, 70.0],
            "nonroi_pcts": [20.0, 30.0, 40.0],
            "achievable_roi_mean_vm": 0.025,
            "best_point": {
                "roi_pct": 80.0,
                "nonroi_pct": 20.0,
                "focality_score": -0.0042,
            },
            "points": [
                {"roi_pct": 80.0, "nonroi_pct": 20.0, "score": -0.0042},
                {"roi_pct": 80.0, "nonroi_pct": 30.0, "score": -0.0038},
            ],
        }

        write_manifest(
            str(tmp_path), config, result, "pareto_label", pareto_data=pareto_data
        )
        data = read_manifest(str(tmp_path))

        assert data["pareto"] is not None
        assert data["pareto"]["roi_pcts"] == [80.0, 70.0]
        assert data["pareto"]["nonroi_pcts"] == [20.0, 30.0, 40.0]
        assert data["pareto"]["achievable_roi_mean_vm"] == 0.025
        assert data["pareto"]["best_point"]["roi_pct"] == 80.0
        assert len(data["pareto"]["points"]) == 2


# ---------------------------------------------------------------------------
# generate_run_dirname
# ---------------------------------------------------------------------------


class TestGenerateRunDirname:
    def test_generate_run_dirname_format(self, tmp_path):
        name = generate_run_dirname(str(tmp_path))
        assert re.match(r"^\d{8}_\d{6}$", name), f"Unexpected format: {name}"

    def test_generate_run_dirname_collision(self, tmp_path):
        # Get the name that would be generated right now
        name1 = generate_run_dirname(str(tmp_path))
        assert re.match(r"^\d{8}_\d{6}$", name1)

        # Create the folder to force collision on next call
        os.makedirs(os.path.join(str(tmp_path), name1))

        # Next call within the same second should get _1 suffix
        name2 = generate_run_dirname(str(tmp_path))
        assert name2 == f"{name1}_1"

        # Create _1 folder to force another collision
        os.makedirs(os.path.join(str(tmp_path), name2))

        name3 = generate_run_dirname(str(tmp_path))
        assert name3 == f"{name1}_2"


# ---------------------------------------------------------------------------
# generate_label
# ---------------------------------------------------------------------------


class TestGenerateLabel:
    def test_generate_label_spherical(self):
        roi = SphericalROI(x=-42.0, y=-20.0, z=55.0, radius=10.0)
        config = _make_config(roi, goal="mean", postproc="max_TI")
        label = generate_label(config)
        assert label == "mean_maxTI_sphere(-42,-20,55)r10"

    def test_generate_label_atlas(self):
        roi = AtlasROI(
            atlas_path="/path/to/lh.aparc.annot", label=1001, hemisphere="lh"
        )
        config = _make_config(roi, goal="mean", postproc="max_TI")
        label = generate_label(config)
        assert label == "mean_maxTI_lh-aparc-1001"

    def test_generate_label_subcortical(self):
        roi = SubcorticalROI(atlas_path="/path/to/aseg.nii.gz", label=11, tissues="GM")
        config = _make_config(roi, goal="focality", postproc="dir_TI_normal")
        label = generate_label(config)
        assert label == "focality_normalTI_subcortical-aseg-11"

    def test_generate_label_pareto(self):
        roi = SphericalROI(x=-42.0, y=-20.0, z=55.0, radius=10.0)
        config = _make_config(roi, goal="focality", postproc="max_TI")
        label = generate_label(config, pareto=True)
        assert label == "pareto_maxTI_sphere(-42,-20,55)r10"


# ---------------------------------------------------------------------------
# parse_optimization_output
# ---------------------------------------------------------------------------


class TestParseOptimizationOutput:
    def test_parse_optimization_output_final_value(self):
        line = "Final goal function value:   -42.123"
        result = parse_optimization_output(line)
        assert result == -42.123

    def test_parse_optimization_output_goal_value(self):
        line = "Goal function value: 0.025"
        result = parse_optimization_output(line)
        assert result == 0.025

    def test_parse_optimization_output_table_row(self):
        line = "|max_TI | 0.025e-03"
        result = parse_optimization_output(line)
        assert abs(result - 0.000025) < 1e-10

    def test_parse_optimization_output_no_match(self):
        line = "INFO: Starting optimization run 3 of 5..."
        result = parse_optimization_output(line)
        assert result is None

    def test_parse_optimization_output_scientific_notation(self):
        line = "Final goal function value:  -4.23e-02"
        result = parse_optimization_output(line)
        assert abs(result - (-0.0423)) < 1e-10

    def test_parse_optimization_output_table_row_no_exponent(self):
        line = "|max_TI | 0.025"
        result = parse_optimization_output(line)
        assert result == 0.025
