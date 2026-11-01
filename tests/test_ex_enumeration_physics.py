"""Ex-search enumerates each physical montage and current split once, and never a dead channel.

What this pins (2026-10-22, package p05 "ex-pool-polarity-duplicates" and "ex-bucket-self-pairs"):

* The physics the pool enumeration relies on: the two-channel TI envelope amplitude is
  unchanged when either channel's polarity flips, or when the two channels swap. Checked with
  ``tit.calc.envelope_max`` (K=1 closed form, real numpy) on random fields, the function the
  engine scores with.
* Pool mode ("any electrode in any position") therefore yields each physical
  ``{pair1 @ I1, pair2 @ I2}`` exactly once: 3 pairings per 4-electrode set, each in one channel
  order when the split list is its own mirror (it contains ``(b, a)`` for every ``(a, b)``) and in
  both orders otherwise. Expected counts are the hand formula ``C(n, 4) * 3 * orders * splits``
  and the expected *set* is a brute force over ``itertools.product(pool, repeat=4)`` reduced to
  physical keys -- neither reads ``tit.opt.ex.logic``.
* Bucket mode never yields a channel whose plus and minus electrode are the same (zero field,
  so TI = 0 and the row is meaningless) and, like mEx (all eight distinct), never shares one
  electrode between the two channels. Overlapping buckets (2026-11-01, S2-5) yield each
  physical montage of the bucket product once, checked against the same brute force over
  ``itertools.product(*buckets)``.
* The ex-search report's top table lists distinct physical montages, also for runs written
  before this fix (Dataset 000 sub-101 ``20260919_160209``: its top 8 rows were one montage).

Reproduce: ``pytest tests/test_ex_enumeration_physics.py -q``
(real-data leg: ``TIT_DATASET_000=/path/to/000 pytest tests/test_ex_enumeration_physics.py``).
"""

from __future__ import annotations

import csv
import logging
import os
import re
from itertools import product
from math import comb
from pathlib import Path

import numpy as np
import pytest

from tit.calc import envelope_max
from tit.opt.ex.engine import ExSearchEngine
from tit.opt.ex.logic import (
    count_combinations,
    _electrode_combinations,
    explain_zero_combinations,
    ratios_mirror_symmetric,
)
from tit.reporting.generators import ex_search

SYMMETRIC_SPLITS = [
    (1.6, 0.4),
    (1.2, 0.8),
    (0.8, 1.2),
    (0.4, 1.6),
]  # 2 mA, step 0.4, limit 1.6
ASYMMETRIC_SPLITS = [
    (1.7, 0.3),
    (1.4, 0.6),
    (1.1, 0.9),
    (0.8, 1.2),
    (0.5, 1.5),
]  # step 0.3


def _ti(e1, e2):
    return envelope_max([e1, e2])


def test_ti_envelope_ignores_channel_polarity_and_order():
    rng = np.random.default_rng(2026)
    e1 = rng.normal(size=(500, 3))
    e2 = rng.normal(size=(500, 3)) * rng.uniform(0.1, 3.0, size=(500, 1))
    reference = _ti(e1, e2)
    assert np.all(reference > 0)
    for variant in (_ti(-e1, e2), _ti(e1, -e2), _ti(-e1, -e2), _ti(e2, e1)):
        np.testing.assert_allclose(variant, reference, rtol=1e-12, atol=1e-15)


def _physical(e1p, e1m, e2p, e2m, split):
    return frozenset(
        {
            (frozenset((e1p, e1m)), round(split[0], 9)),
            (frozenset((e2p, e2m)), round(split[1], 9)),
        }
    )


def _quads(lists, pool, splits):
    """The electrode quads the runner evaluates (``ExSearchEngine.run``)."""
    return list(
        _electrode_combinations(
            *lists, pool, both_channel_orders=not ratios_mirror_symmetric(splits)
        )
    )


def _brute_force_physical(pool, splits):
    labels = list(dict.fromkeys(pool))
    return {
        _physical(*quad, split)
        for quad in product(labels, repeat=4)
        if len(set(quad)) == 4
        for split in splits
    }


@pytest.mark.parametrize(
    "pool,splits,orders",
    [
        (["A", "B", "C", "D"], SYMMETRIC_SPLITS, 1),
        (["A", "B", "C", "D", "E"], SYMMETRIC_SPLITS, 1),
        (["A", "B", "C", "D", "E", "F"], [(1.0, 1.0)], 1),
        (["A", "B", "C", "D", "E"], ASYMMETRIC_SPLITS, 2),
        (["A", "B", "C", "D", "E", "F", "G", "H"], ASYMMETRIC_SPLITS, 2),
    ],
)
def test_pool_yields_every_physical_montage_and_split_exactly_once(
    pool, splits, orders
):
    quads = _quads([pool] * 4, True, splits)
    keys = [_physical(*quad, split) for quad in quads for split in splits]
    assert len(keys) == len(set(keys)), "a physical montage+split is evaluated twice"
    assert set(keys) == _brute_force_physical(pool, splits)
    n = len(pool)
    assert len(keys) == comb(n, 4) * 3 * orders * len(splits)
    assert count_combinations(pool, pool, pool, pool, splits, True) == len(keys)


def test_pool_counts_a_duplicated_label_once():
    pool = ["A", "B", "A", "C", "D"]
    n_rows = len(_quads([pool, [], [], []], True, SYMMETRIC_SPLITS)) * len(
        SYMMETRIC_SPLITS
    )
    assert n_rows == comb(4, 4) * 3 * len(SYMMETRIC_SPLITS)
    assert count_combinations(pool, [], [], [], SYMMETRIC_SPLITS, True) == n_rows


def test_bucket_mode_drops_self_pairs():
    electrodes = _quads([["A", "B"], ["A", "B"], ["C"], ["D"]], False, [(1.0, 1.0)])
    # By hand: (A, A) and (B, B) carry no current between poles, and (B, A) is (A, B)
    # with channel 1's polarity flipped -- the same stimulation.
    assert electrodes == [("A", "B", "C", "D")]
    assert (
        count_combinations(["A", "B"], ["A", "B"], ["C"], ["D"], [(1.0, 1.0)], False)
        == 1
    )


def _brute_force_physical_buckets(buckets, splits):
    return {
        _physical(*quad, split)
        for quad in product(*buckets)
        if len(set(quad)) == 4
        for split in splits
    }


@pytest.mark.parametrize(
    "buckets",
    [
        [["A", "B", "C", "D"]] * 4,
        [["A", "B", "C"], ["A", "B", "C"], ["E", "F"], ["G", "H"]],
        [["A", "B"], ["C", "D"], ["C", "D"], ["A", "B"]],
        [["A", "B", "C"], ["D", "E"], ["B", "D", "F"], ["A", "E", "C", "G"]],
        [["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
    ],
)
@pytest.mark.parametrize("splits", [SYMMETRIC_SPLITS, ASYMMETRIC_SPLITS])
def test_overlapping_buckets_yield_every_physical_montage_and_split_exactly_once(
    buckets, splits
):
    quads = _quads(buckets, False, splits)
    keys = [_physical(*quad, split) for quad in quads for split in splits]
    assert len(keys) == len(set(keys)), "a physical montage+split is evaluated twice"
    assert set(keys) == _brute_force_physical_buckets(buckets, splits)
    assert count_combinations(*buckets, splits, False) == len(keys)


def _random_overlapping_buckets(rng, labels):
    return [
        [label for label in labels if rng.random() < 0.6] * rng.integers(1, 3)
        for _ in range(4)
    ]


@pytest.mark.parametrize("splits", [SYMMETRIC_SPLITS, ASYMMETRIC_SPLITS])
def test_random_overlapping_buckets_lose_no_physical_montage(splits):
    # The proof that dropping equivalent tuples drops no stimulation: the physical montage+split
    # set of the kept tuples equals the one of every distinct tuple of the product.
    rng = np.random.default_rng(20261101)
    for _ in range(60):
        buckets = _random_overlapping_buckets(rng, "ABCDEFG")
        quads = _quads(buckets, False, splits)
        keys = [_physical(*quad, split) for quad in quads for split in splits]
        assert len(keys) == len(set(keys)), buckets
        assert set(keys) == _brute_force_physical_buckets(buckets, splits), buckets
        assert all(
            all(e in b for e, b in zip(quad, buckets)) and len(set(quad)) == 4
            for quad in quads
        ), "a kept tuple is not an assignment of the buckets"
        assert count_combinations(*buckets, splits, False) == len(keys)


MIRROR = {"A": "B", "B": "A", "C": "D", "D": "C", "E": "F", "F": "E", "G": "G"}


@pytest.mark.parametrize("pairing", ["within_pairs", "cross_pairs"])
@pytest.mark.parametrize("splits", [SYMMETRIC_SPLITS, ASYMMETRIC_SPLITS])
def test_symmetric_search_evaluates_each_physical_montage_once(pairing, splits):
    def mirrored(a, b, c, d):
        if pairing == "within_pairs":
            return MIRROR.get(a) == b and MIRROR.get(c) == d
        return MIRROR.get(a) == c and MIRROR.get(b) == d

    rng = np.random.default_rng(20261102)
    for _ in range(60):
        buckets = _random_overlapping_buckets(rng, "ABCDEFG")
        expected = {
            _physical(*quad, split)
            for quad in product(*buckets)
            if len(set(quad)) == 4 and mirrored(*quad)
            for split in splits
        }
        quads = list(
            _electrode_combinations(
                *buckets,
                False,
                MIRROR,
                pairing,
                both_channel_orders=not ratios_mirror_symmetric(splits),
            )
        )
        keys = [_physical(*quad, split) for quad in quads for split in splits]
        assert len(keys) == len(set(keys)), buckets
        assert set(keys) == expected, buckets
        assert all(mirrored(*quad) for quad in quads)
        assert count_combinations(*buckets, splits, False, MIRROR, pairing) == len(keys)


def test_bucket_mode_never_shares_an_electrode_between_channels():
    quads = _quads([["A"], ["B"], ["A", "C"], ["D", "B"]], False, [(1.0, 1.0)])
    # Product is 1*1*2*2 = 4 tuples; only C-D for channel 2 keeps all four distinct.
    assert quads == [("A", "B", "C", "D")]


def test_bucket_mode_with_no_distinct_montage_explains_why():
    buckets = (["A"], ["A"], ["B"], ["C"])
    assert count_combinations(*buckets, [(1.0, 1.0)], False) == 0
    reason = explain_zero_combinations(*buckets, [(1.0, 1.0)], False)
    assert "distinct" in reason and "e1_plus" not in reason


class _FakeTI:
    @staticmethod
    def get_field(spec, leadfield, idx):
        plus, minus, current = spec
        return current * (leadfield[idx.index(plus)] - leadfield[idx.index(minus)])


def test_engine_pool_rows_are_distinct_physical_montages(monkeypatch, tmp_path):
    monkeypatch.setattr("tit.opt.ex.engine.TI", _FakeTI)
    pool = ["AF7", "AFz", "CP6", "P10", "POz"]
    engine = ExSearchEngine("x.hdf5", "roi.csv", "t", logging.getLogger("t"))
    engine.leadfield = np.random.default_rng(3).normal(size=(5, 30, 3))
    engine.idx_lf = list(pool)
    engine.roi_indices, engine.roi_volumes = np.arange(6), np.ones(6)
    engine.gm_indices, engine.gm_volumes = np.arange(30), np.ones(30)
    results = engine.run(
        pool, pool, pool, pool, SYMMETRIC_SPLITS, True, str(tmp_path), n_jobs=1
    )
    # The audit's probe: this pool and sweep used to write 480 rows for 60 physical ones.
    assert len(results) == 60
    keys = {
        _physical(*r["electrodes"], (r["current_ch1_mA"], r["current_ch2_mA"]))
        for r in results.values()
    }
    assert keys == _brute_force_physical(pool, SYMMETRIC_SPLITS)


# ── the report's top table ─────────────────────────────────────────────────────────

_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def _top_table_keys(html: str) -> list:
    table = html.split("Top 25 by composite", 1)[1].split("</table>", 1)[0]
    keys = []
    for row in _ROW.findall(table):
        cells = [re.sub(r"<[^>]+>", "", c) for c in _CELL.findall(row)]
        if not cells:
            continue
        currents = [float(v) for v in cells[3].split("/")]
        keys.append(
            frozenset(
                {
                    (
                        frozenset(re.sub(r"\([+−]\)", "", cells[1]).split("–")),
                        currents[0],
                    ),
                    (
                        frozenset(re.sub(r"\([+−]\)", "", cells[2]).split("–")),
                        currents[1],
                    ),
                }
            )
        )
    return keys


def _write_csv(path: Path, rows: list[tuple]) -> None:
    with path.open("w", newline="") as stream:
        out = csv.writer(stream)
        out.writerow(
            [
                "Montage",
                "Current_Ch1_mA",
                "Current_Ch2_mA",
                "TImax_ROI",
                "TImean_ROI",
                "TImean_GM",
                "Focality",
                "Composite_Index",
            ]
        )
        for montage, i1, i2, mean, foc in rows:
            out.writerow([montage, i1, i2, mean * 2, mean, 0.05, foc, mean * foc])


def _report_rows(run_dir: Path) -> tuple[list, str]:
    rec = {
        "run": run_dir.name,
        "config": {"leadfield_hdf": "x_leadfield_EEG10-10.hdf5", "roi_radius": 3},
        "rows": ex_search.read_results(run_dir / "final_output.csv"),
        "roi": {},
        "leadfield": {},
    }
    return rec["rows"], ex_search.build_html(rec, "101")


def test_report_top_table_lists_each_physical_montage_once(tmp_path):
    # One physical montage written four times (both polarities of each channel), as the
    # pre-fix pool enumeration did, plus 30 other distinct montages ranked below it.
    duplicates = [
        (f"{a}_{b} <> {c}_{d}_I1-1.2mA_I2-0.8mA", 1.2, 0.8, 0.2, 1.1)
        for a, b in (("AF7", "P10"), ("P10", "AF7"))
        for c, d in (("AFz", "POz"), ("POz", "AFz"))
    ]
    others = [
        (
            f"E{k}_E{k + 1} <> E{k + 2}_E{k + 3}_I1-1.0mA_I2-1.0mA",
            1.0,
            1.0,
            0.1,
            1.0 - k / 100,
        )
        for k in range(0, 120, 4)
    ]
    _write_csv(tmp_path / "final_output.csv", duplicates + others)
    rows, html = _report_rows(tmp_path)
    keys = _top_table_keys(html)
    assert len(keys) == 25
    assert len(set(keys)) == 25
    assert keys[0] == frozenset(
        {(frozenset({"AF7", "P10"}), 1.2), (frozenset({"AFz", "POz"}), 0.8)}
    )
    # The headline still counts every evaluated row.
    assert f"leads {len(rows):,} montages" in html


_DATASET = os.environ.get("TIT_DATASET_000", "")
_RUN = Path(_DATASET) / "derivatives/SimNIBS/sub-101/ex-search/20260919_160209"


@pytest.mark.skipif(
    not _DATASET or not (_RUN / "final_output.csv").is_file(),
    reason="skipping: TIT_DATASET_000 unset or sub-101 ex-search run 20260919_160209 absent",
)
def test_report_of_a_real_pre_fix_pool_run_has_distinct_top_rows():
    before = {p: p.stat().st_mtime_ns for p in _RUN.rglob("*") if p.is_file()}
    rows = ex_search.read_results(_RUN / "final_output.csv")
    # Precondition from the audit: the old pool run repeats its winner (4 polarities x 2 orders).
    winner = _physical(
        *rows[0]["pairs"][0], *rows[0]["pairs"][1], (rows[0]["I1"], rows[0]["I2"])
    )
    repeats = sum(
        _physical(*r["pairs"][0], *r["pairs"][1], (r["I1"], r["I2"])) == winner
        for r in rows
    )
    assert repeats > 1
    rec = ex_search.collect(_RUN)
    keys = _top_table_keys(ex_search.build_html(rec, "101"))
    assert len(keys) == len(set(keys)) == 25
    after = {p: p.stat().st_mtime_ns for p in _RUN.rglob("*") if p.is_file()}
    assert after == before
