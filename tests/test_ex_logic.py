#!/usr/bin/env python3
"""
Tests for tit/opt/ex/logic.py and tit/opt/ex/results.py.

Covers combinatorial montage/current generation and result serialization.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure repo root is on sys.path.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.opt.ex.logic import (
    _electrode_combinations,
    count_combinations,
    generate_current_ratios,
    generate_montage_combinations,
)
from tit.opt.ex.results import (
    build_csv_rows,
    save_csv,
)

# ===========================================================================
# generate_current_ratios
# ===========================================================================


@pytest.mark.unit
class TestGenerateCurrentRatios:
    """Tests for generate_current_ratios()."""

    def test_symmetric_split(self):
        """Equal total_current split: 2.0 mA total, 0.5 step, 2.0 limit."""
        ratios = generate_current_ratios(2.0, 0.5, 2.0)
        # ch1 goes from 2.0 down; valid pairs where both >= 0.5 and <= 2.0
        # ch1=1.5,ch2=0.5 | ch1=1.0,ch2=1.0 | ch1=0.5,ch2=1.5
        # ch1=2.0,ch2=0.0 -> ch2 < 0.5, skip
        assert len(ratios) == 3
        # First ratio has highest ch1
        assert abs(ratios[0][0] - 1.5) < 1e-9
        assert abs(ratios[0][1] - 0.5) < 1e-9
        # Symmetric middle
        assert abs(ratios[1][0] - 1.0) < 1e-9
        assert abs(ratios[1][1] - 1.0) < 1e-9

    def test_single_step_equals_total(self):
        """total_current == channel_limit == step produces one ratio."""
        ratios = generate_current_ratios(2.0, 1.0, 2.0)
        # ch1=2.0 -> ch2=0.0 skip; ch1=1.0 -> ch2=1.0 valid
        assert len(ratios) == 1
        assert abs(ratios[0][0] - 1.0) < 1e-9
        assert abs(ratios[0][1] - 1.0) < 1e-9

    def test_large_step_no_valid_ratios(self):
        """Step larger than half total => no valid ratios."""
        # total=2.0, step=1.5, limit=2.0
        # ch1 starts at 2.0, decrements by 1.5 -> ch1=2.0 (ch2=0.0<1.5 skip), ch1=0.5 (< 1.5 skip)
        ratios = generate_current_ratios(2.0, 1.5, 2.0)
        assert len(ratios) == 0

    def test_fine_step(self):
        """Small step size produces many ratios."""
        ratios = generate_current_ratios(2.0, 0.1, 2.0)
        # Valid: ch1 from 1.9 down to 0.1 in 0.1 steps = 19 values
        assert len(ratios) == 19

    def test_ratios_sum_to_total(self):
        """Every ratio pair should sum to total_current."""
        ratios = generate_current_ratios(3.0, 0.5, 3.0)
        for ch1, ch2 in ratios:
            assert abs(ch1 + ch2 - 3.0) < 1e-9

    def test_ratios_within_limits(self):
        """All ratio values respect channel_limit and minimum step."""
        limit = 1.5
        step = 0.25
        ratios = generate_current_ratios(2.0, step, limit)
        for ch1, ch2 in ratios:
            assert ch1 <= limit + step * 0.01
            assert ch2 <= limit + step * 0.01
            assert ch1 >= step - step * 0.01
            assert ch2 >= step - step * 0.01

    def test_ratios_descending_ch1(self):
        """ch1 values are generated in descending order."""
        ratios = generate_current_ratios(2.0, 0.25, 2.0)
        ch1_vals = [r[0] for r in ratios]
        assert ch1_vals == sorted(ch1_vals, reverse=True)


# ===========================================================================
# _electrode_combinations
# ===========================================================================


@pytest.mark.unit
class TestElectrodeCombinations:
    """Tests for _electrode_combinations()."""

    def test_bucket_mode(self):
        """Non-all_combinations: Cartesian product of 4 buckets."""
        combos = list(
            _electrode_combinations(["A"], ["B"], ["C"], ["D"], all_combinations=False)
        )
        assert combos == [("A", "B", "C", "D")]

    def test_bucket_mode_multiple(self):
        """Multiple electrodes per bucket produce full Cartesian product."""
        combos = list(
            _electrode_combinations(
                ["A1", "A2"], ["B1"], ["C1"], ["D1"], all_combinations=False
            )
        )
        assert len(combos) == 2
        assert ("A1", "B1", "C1", "D1") in combos
        assert ("A2", "B1", "C1", "D1") in combos

    def test_bucket_mode_count(self):
        """Bucket mode count = product of bucket sizes."""
        combos = list(
            _electrode_combinations(
                ["A1", "A2"],
                ["B1", "B2"],
                ["C1", "C2"],
                ["D1", "D2"],
                all_combinations=False,
            )
        )
        assert len(combos) == 2 * 2 * 2 * 2

    def test_all_combinations_mode(self):
        """all_combinations=True: permutations of 4 from e1_plus pool, all unique."""
        pool = ["E1", "E2", "E3", "E4"]
        combos = list(_electrode_combinations(pool, [], [], [], all_combinations=True))
        # 4 electrodes choose 4 with order, all distinct = 4! = 24
        assert len(combos) == 24
        for combo in combos:
            assert len(set(combo)) == 4

    def test_all_combinations_too_few_electrodes(self):
        """Pool of 3 electrodes can't form 4-tuples with all unique."""
        pool = ["E1", "E2", "E3"]
        combos = list(_electrode_combinations(pool, [], [], [], all_combinations=True))
        assert len(combos) == 0

    def test_all_combinations_five_electrodes(self):
        """5 electrodes: P(5,4) = 120 unique 4-tuples."""
        pool = ["E1", "E2", "E3", "E4", "E5"]
        combos = list(_electrode_combinations(pool, [], [], [], all_combinations=True))
        assert len(combos) == 120

    def test_all_combinations_ignores_other_buckets(self):
        """In all_combinations mode, only e1_plus is used."""
        pool = ["E1", "E2", "E3", "E4"]
        combos_a = list(
            _electrode_combinations(pool, ["X"], ["Y"], ["Z"], all_combinations=True)
        )
        combos_b = list(
            _electrode_combinations(pool, [], [], [], all_combinations=True)
        )
        assert combos_a == combos_b


# ===========================================================================
# generate_montage_combinations
# ===========================================================================


@pytest.mark.unit
class TestGenerateMontagesCombinations:
    """Tests for generate_montage_combinations()."""

    def test_basic_output_structure(self):
        """Each yielded tuple has 5 elements: 4 electrodes + ratio tuple."""
        ratios = [(1.0, 1.0)]
        combos = list(
            generate_montage_combinations(
                ["A"], ["B"], ["C"], ["D"], ratios, all_combinations=False
            )
        )
        assert len(combos) == 1
        assert combos[0] == ("A", "B", "C", "D", (1.0, 1.0))

    def test_multiple_ratios_multiply_combos(self):
        """Each electrode combo is paired with every ratio."""
        ratios = [(1.5, 0.5), (1.0, 1.0), (0.5, 1.5)]
        combos = list(
            generate_montage_combinations(
                ["A"], ["B"], ["C"], ["D"], ratios, all_combinations=False
            )
        )
        assert len(combos) == 3
        assert combos[0][4] == (1.5, 0.5)
        assert combos[1][4] == (1.0, 1.0)
        assert combos[2][4] == (0.5, 1.5)

    def test_total_count_matches(self):
        """Total combinations = electrode combos * current ratios."""
        e1p, e1m, e2p, e2m = ["A1", "A2"], ["B1"], ["C1", "C2"], ["D1"]
        ratios = [(1.0, 1.0), (0.5, 1.5)]
        combos = list(generate_montage_combinations(e1p, e1m, e2p, e2m, ratios, False))
        # electrode combos: 2*1*2*1 = 4, ratios: 2, total: 8
        assert len(combos) == 8

    def test_all_combinations_mode_with_ratios(self):
        """Pool mode with multiple ratios."""
        pool = ["E1", "E2", "E3", "E4"]
        ratios = [(1.0, 1.0), (0.5, 1.5)]
        combos = list(generate_montage_combinations(pool, [], [], [], ratios, True))
        # 24 electrode combos * 2 ratios = 48
        assert len(combos) == 48


# ===========================================================================
# count_combinations
# ===========================================================================


@pytest.mark.unit
class TestCountCombinations:
    """Tests for count_combinations()."""

    def test_matches_generated_length(self):
        """count_combinations should equal len(list(generate_montage_combinations))."""
        e1p, e1m, e2p, e2m = ["A1", "A2"], ["B1", "B2"], ["C1"], ["D1", "D2"]
        ratios = [(1.0, 1.0), (0.5, 1.5), (1.5, 0.5)]
        count = count_combinations(e1p, e1m, e2p, e2m, ratios, False)
        actual = list(generate_montage_combinations(e1p, e1m, e2p, e2m, ratios, False))
        assert count == len(actual)

    def test_all_combinations_count(self):
        """Pool mode count matches."""
        pool = ["E1", "E2", "E3", "E4", "E5"]
        ratios = [(1.0, 1.0)]
        count = count_combinations(pool, [], [], [], ratios, True)
        assert count == 120  # P(5,4) * 1 ratio

    def test_zero_ratios_gives_zero(self):
        """No current ratios means zero combinations."""
        count = count_combinations(["A"], ["B"], ["C"], ["D"], [], False)
        assert count == 0


# ===========================================================================
# build_csv_rows
# ===========================================================================


def _make_results(n=2, roi="region"):
    """Build a synthetic results dict for testing."""
    results = {}
    for i in range(n):
        mesh_name = f"TI_field_E{i}_and_E{i+1}.msh"
        results[mesh_name] = {
            f"{roi}_TImax_ROI": 0.5 + i * 0.1,
            f"{roi}_TImean_ROI": 0.3 + i * 0.05,
            f"{roi}_TImean_GM": 0.2 + i * 0.02,
            f"{roi}_Focality": 0.8 - i * 0.1,
            "current_ch1_mA": 1.0,
            "current_ch2_mA": 1.0,
        }
    return results


@pytest.mark.unit
class TestBuildCsvRows:
    """Tests for build_csv_rows()."""

    def test_header_row(self):
        """First row is the header with 8 columns."""
        results = _make_results(1)
        rows, *_ = build_csv_rows(results, "region")
        assert rows[0][0] == "Montage"
        assert "Composite_Index" in rows[0]
        assert len(rows[0]) == 8

    def test_data_row_has_8_elements(self):
        """Each data row has 8 elements matching the header."""
        results = _make_results(1)
        rows, *_ = build_csv_rows(results, "region")
        assert len(rows[1]) == 8

    def test_row_count(self):
        """Number of data rows equals number of results + 1 header."""
        results = _make_results(5)
        rows, *_ = build_csv_rows(results, "region")
        assert len(rows) == 6  # 1 header + 5 data

    def test_metric_arrays_length(self):
        """Metric arrays have same length as results."""
        results = _make_results(3)
        _, timax, timean, foc, comp = build_csv_rows(results, "region")
        assert len(timax) == 3
        assert len(timean) == 3
        assert len(foc) == 3
        assert len(comp) == 3

    def test_composite_is_product(self):
        """Composite index = TImean * Focality."""
        results = _make_results(2)
        rows, _, timean, foc, comp = build_csv_rows(results, "region")
        for i in range(len(comp)):
            assert abs(comp[i] - timean[i] * foc[i]) < 1e-9

    def test_montage_name_formatting(self):
        """Mesh name regex replaces _and_ with <>."""
        results = {
            "TI_field_A1_and_B2.msh": {
                "roi_TImax_ROI": 1.0,
                "roi_TImean_ROI": 0.5,
                "roi_TImean_GM": 0.3,
                "roi_Focality": 0.8,
            }
        }
        rows, *_ = build_csv_rows(results, "roi")
        assert " <> " in rows[1][0]

    def test_missing_current_defaults_to_zero(self):
        """Missing current keys default to 0."""
        results = {
            "TI_field_X.msh": {
                "roi_TImax_ROI": 1.0,
                "roi_TImean_ROI": 0.5,
                "roi_TImean_GM": 0.3,
                "roi_Focality": 0.8,
            }
        }
        rows, *_ = build_csv_rows(results, "roi")
        assert rows[1][1] == "0.0"  # current_ch1_mA
        assert rows[1][2] == "0.0"  # current_ch2_mA

    def test_empty_results(self):
        """Empty results dict produces header-only rows."""
        rows, timax, timean, foc, comp = build_csv_rows({}, "roi")
        assert len(rows) == 1  # header only
        assert timax == []


# ===========================================================================
# save_csv
# ===========================================================================


@pytest.mark.unit
class TestSaveCsv:
    """Tests for save_csv()."""

    def test_writes_file(self, tmp_path):
        """CSV file is created on disk."""
        results = _make_results(2)
        logger = MagicMock()
        path = save_csv(results, "region", str(tmp_path), logger)
        assert os.path.exists(path)
        assert path.endswith("final_output.csv")

    def test_csv_content_readable(self, tmp_path):
        """Written CSV has correct number of lines."""
        results = _make_results(3)
        path = save_csv(results, "region", str(tmp_path), MagicMock())
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 4  # 1 header + 3 data rows

    def test_logs_output(self, tmp_path):
        """Logger is called."""
        logger = MagicMock()
        save_csv(_make_results(1), "region", str(tmp_path), logger)
        logger.info.assert_called_once()
