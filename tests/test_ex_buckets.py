"""Tests for ex-search electrode bucket helpers."""

import json

import pytest

from tit.opt.ex.buckets import (
    build_electrode_mirror_map,
    build_quadrant_buckets,
    canonical_template_coord_path,
    load_bucket_file,
    normalize_buckets,
    save_bucket_file,
)


@pytest.mark.unit
class TestNormalizeBuckets:
    def test_accepts_gui_style_keys(self):
        buckets = normalize_buckets(
            {
                "E1+": "F3, F5",
                "E1-": ["F4", "F6"],
                "E2+": "P3; P5",
                "E2-": ["P4"],
            }
        )

        assert buckets["e1_plus"] == ["F3", "F5"]
        assert buckets["e1_minus"] == ["F4", "F6"]
        assert buckets["e2_plus"] == ["P3", "P5"]
        assert buckets["e2_minus"] == ["P4"]


@pytest.mark.unit
class TestBucketFiles:
    def test_loads_json_bucket_file(self, tmp_path):
        path = tmp_path / "buckets.json"
        path.write_text(
            json.dumps(
                {
                    "E1+": ["LA1", "LA2"],
                    "E1-": ["RA1"],
                    "E2+": ["LP1"],
                    "E2-": ["RP1", "RP2"],
                }
            )
        )

        buckets = load_bucket_file(path)

        assert buckets["e1_plus"] == ["LA1", "LA2"]
        assert buckets["e2_minus"] == ["RP1", "RP2"]

    def test_loads_csv_bucket_file(self, tmp_path):
        path = tmp_path / "buckets.csv"
        path.write_text(
            "\n".join(
                [
                    "E1+,LA1,LA2",
                    "E1-,RA1",
                    "E2+,LP1;LP2",
                    "E2-,RP1,RP2",
                ]
            )
        )

        buckets = load_bucket_file(path)

        assert buckets["e1_plus"] == ["LA1", "LA2"]
        assert buckets["e2_plus"] == ["LP1", "LP2"]

    def test_saves_json_bucket_file(self, tmp_path):
        path = tmp_path / "buckets.json"
        save_bucket_file(
            path,
            {
                "e1_plus": ["LA1"],
                "e1_minus": ["RA1"],
                "e2_plus": ["LP1"],
                "e2_minus": ["RP1"],
            },
        )

        assert json.loads(path.read_text())["e1_plus"] == ["LA1"]


@pytest.mark.unit
class TestQuadrantBuckets:
    def test_builds_quadrant_buckets_from_eeg_csv(self, tmp_path):
        path = tmp_path / "cap.csv"
        path.write_text(
            "\n".join(
                [
                    "Electrode,-1,2,0,LA",
                    "Electrode,1,2,0,RA",
                    "Electrode,-1,-2,0,LP",
                    "Electrode,1,-2,0,RP",
                    "Fiducial,0,0,0,Nz",
                ]
            )
        )

        buckets = build_quadrant_buckets(path)

        assert buckets == {
            "e1_plus": ["LA"],
            "e1_minus": ["RA"],
            "e2_plus": ["LP"],
            "e2_minus": ["RP"],
        }


@pytest.mark.unit
class TestElectrodeMirrorMap:
    def test_builds_left_right_mirrors_from_eeg_csv(self, tmp_path):
        path = tmp_path / "cap.csv"
        path.write_text(
            "\n".join(
                [
                    "Electrode,-1,2,0,LA",
                    "Electrode,1,2,0,RA",
                    "Electrode,-1,-2,0,LP",
                    "Electrode,1,-2,0,RP",
                    "Electrode,0,0,0,Cz",
                ]
            )
        )

        mirror_map = build_electrode_mirror_map(path)

        assert mirror_map["LA"] == "RA"
        assert mirror_map["RA"] == "LA"
        assert mirror_map["LP"] == "RP"
        assert mirror_map["RP"] == "LP"
        assert mirror_map["Cz"] == "Cz"

    def test_builds_mirrors_from_template_xy_csv(self, tmp_path):
        path = tmp_path / "template.csv"
        path.write_text(
            "\n".join(
                [
                    "electrode_name,x,y",
                    "E1,-2,1",
                    "E2,2,1",
                ]
            )
        )

        mirror_map = build_electrode_mirror_map(path)

        assert mirror_map == {"E1": "E2", "E2": "E1"}

    def test_builds_mirrors_from_positive_image_xy_csv(self, tmp_path):
        path = tmp_path / "template.csv"
        path.write_text(
            "\n".join(
                [
                    "electrode_name,x,y",
                    "L,10,5",
                    "R,30,5",
                    "C,20,5",
                ]
            )
        )

        mirror_map = build_electrode_mirror_map(path)

        assert mirror_map["L"] == "R"
        assert mirror_map["R"] == "L"
        assert mirror_map["C"] == "C"

    def test_uses_z_coordinate_for_simnibs_eeg_csv_mirrors(self, tmp_path):
        path = tmp_path / "cap.csv"
        path.write_text(
            "\n".join(
                [
                    "Electrode,-10,5,20,L",
                    "Electrode,10,5,80,R_wrong_z",
                    "Electrode,11,5,21,R_good_z",
                ]
            )
        )

        mirror_map = build_electrode_mirror_map(path)

        assert mirror_map["L"] == "R_good_z"

    def test_resolves_canonical_gsn_template(self):
        path = canonical_template_coord_path("GSN-HydroCel-256")

        assert path is not None
        assert path.name == "GSN-256.csv"
