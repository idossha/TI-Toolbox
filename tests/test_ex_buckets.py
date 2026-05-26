"""Tests for ex-search electrode bucket helpers."""

import json

import pytest

from tit.opt.ex.buckets import (
    build_quadrant_buckets,
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
