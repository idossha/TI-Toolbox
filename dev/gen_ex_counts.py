#!/usr/bin/env python3
"""Write tests/fixtures/ex_search_counts.json: the search-space size of each Ex/mEx case.

One table, three readers: ``tests/test_ex_search_counts.py`` (``count_combinations``,
``count_multipolar_combinations`` and ``POST /api/plan/{ex,mex}``) and
``desktop/tests/unit/optimizer-ex-counts.test.ts`` (``exCost`` / ``mexCost``). The desktop cost
line, the server plan and the runner must all equal ``expected_combinations``.

Every number here is a brute force that imports nothing from ``tit``:

* the current splits are hand-checked lists (short ones literal, long ones the arithmetic spec
  ``c1 = total - k * step`` for ``k = 1..``, both channels within ``[step, limit]``); no limit is
  the single balanced split ``(total / 2, total / 2)`` (``ExConfig.channel_limit=None``);
* Ex counts distinct *physical* stimulations: each ``itertools.product`` tuple with four
  distinct electrodes (of the four buckets, or ``product(pool, repeat=4)``), at each split,
  reduced to ``{(pair1 as a set, I1), (pair2 as a set, I2)}`` -- the two-channel TI envelope
  ignores channel polarity and channel order (a label listed twice is one electrode);
* mEx bucket mode counts ``itertools.product`` tuples whose electrodes are all distinct.

Regenerate: ``python3 dev/gen_ex_counts.py`` (a few seconds: the 8 x 8-electrode mEx case walks
8^8 tuples). The output is deterministic; ``git diff`` after a run should be empty.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

OUT = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ex_search_counts.json"
)
EX_KEYS = ("e1_plus", "e1_minus", "e2_plus", "e2_minus")
MEX_KEYS = EX_KEYS + ("e3_plus", "e3_minus", "e4_plus", "e4_minus")


def _spec(total: float, step: float, count: int) -> list[list[float]]:
    return [
        [round(total - step * k, 9), round(step * k, 9)] for k in range(1, count + 1)
    ]


# Hand-checked splits, (channel 1, channel 2) mA, in the sweep's order (channel 1 descending).
SPLITS = {
    # 2 mA, step 0.5, no limit: the balanced split only.
    "2_0.5_none": [[1.0, 1.0]],
    # 2 mA, step 0.5, limit 1.5: 1.5/0.5, 1/1, 0.5/1.5.
    "2_0.5_1.5": [[1.5, 0.5], [1.0, 1.0], [0.5, 1.5]],
    # 2 mA, step 0.4, limit 1.6: both channels in [0.4, 1.6].
    "2_0.4_1.6": [[1.6, 0.4], [1.2, 0.8], [0.8, 1.2], [0.4, 1.6]],
    # 2 mA, step 0.3, limit 1.7: 1.7 down to 0.5; 0.2 is below one step.
    "2_0.3_1.7": [[1.7, 0.3], [1.4, 0.6], [1.1, 0.9], [0.8, 1.2], [0.5, 1.5]],
    # 2 mA, step 0.2, limit 1.8: nine splits 1.8 ... 0.2.
    "2_0.2_1.8": _spec(2.0, 0.2, 9),
    # 2 mA, step 0.05, limit 1.95: 39 splits 1.95 ... 0.05.
    "2_0.05_1.95": _spec(2.0, 0.05, 39),
    # 2 mA, step 0.01, limit 1.99: 199 splits 1.99 ... 0.01.
    "2_0.01_1.99": _spec(2.0, 0.01, 199),
    # Limit 0.8 < total/2: the partner channel would need 1.2 > 0.8 -> nothing.
    "2_0.2_0.8": [],
    # Limit = total/2: only the balanced split.
    "2_0.2_1.0": [[1.0, 1.0]],
    # Off-grid limit 1.5 with step 0.4: 1.5/0.5, 1.1/0.9, 0.7/1.3 (not its own mirror).
    "2_0.4_1.5": [[1.5, 0.5], [1.1, 0.9], [0.7, 1.3]],
}


def _sweep(key: str) -> dict:
    total, step, limit = key.split("_")
    return {
        "total_current": float(total),
        "current_step": float(step),
        "channel_limit": None if limit == "none" else float(limit),
        "splits": SPLITS[key],
    }


def _distinct_tuples(buckets: list[list[str]]) -> int:
    unique = [list(dict.fromkeys(b)) for b in buckets]
    return sum(1 for t in product(*unique) if len(set(t)) == len(t))


def _physical(buckets: list[list[str]], splits: list[list[float]]) -> int:
    unique = [list(dict.fromkeys(b)) for b in buckets]
    keys = {
        frozenset(
            {
                (frozenset(quad[:2]), round(i1, 9)),
                (frozenset(quad[2:]), round(i2, 9)),
            }
        )
        for quad in product(*unique)
        if len(set(quad)) == 4
        for i1, i2 in splits
    }
    return len(keys)


def ex_bucket(case_id: str, buckets: list[list[str]], sweep: str, why: str) -> dict:
    s = _sweep(sweep)
    combos = _physical(buckets, s["splits"])
    # With no split nothing runs, but the montages exist: count them at the balanced split.
    montages = _physical(buckets, s["splits"] or [[1.0, 1.0]])
    return {
        "id": case_id,
        "kind": "ex",
        "why": why,
        "mode": "bucketed",
        "buckets": dict(zip(EX_KEYS, buckets)),
        **s,
        "expected_montages": montages // max(1, len(s["splits"])),
        "expected_combinations": combos,
    }


def ex_pool(case_id: str, pool: list[str], sweep: str, why: str) -> dict:
    s = _sweep(sweep)
    combos = _physical([pool] * 4, s["splits"])
    return {
        "id": case_id,
        "kind": "ex",
        "why": why,
        "mode": "all",
        "pool": pool,
        **s,
        "expected_montages": combos // len(s["splits"]) if s["splits"] else 0,
        "expected_combinations": combos,
    }


def mex_bucket(case_id: str, buckets: list[list[str]], why: str) -> dict:
    n = _distinct_tuples(buckets)
    return {
        "id": case_id,
        "kind": "mex",
        "why": why,
        "buckets": dict(zip(MEX_KEYS, buckets)),
        "current_mA": 1.0,
        "expected_montages": n,
        "expected_combinations": n,
    }


EIGHT = ["F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2"]


def cases() -> list[dict]:
    return [
        ex_pool(
            "pool4", ["F3", "F4", "P3", "P4"], "2_0.5_none", "smallest pool, no limit"
        ),
        ex_pool(
            "pool4_sweep", ["F3", "F4", "P3", "P4"], "2_0.5_1.5", "a 3-split sweep"
        ),
        ex_pool(
            "pool5_audit",
            ["AF7", "AFz", "CP6", "P10", "POz"],
            "2_0.4_1.6",
            "Dataset 000 sub-101 run 20260919_160209: 480 rows for 60 stimulations",
        ),
        ex_pool(
            "pool8_asymmetric",
            EIGHT,
            "2_0.3_1.7",
            "split list not its own mirror: both channel orders count",
        ),
        ex_pool(
            "pool_duplicate_label",
            ["F3", "F4", "F3", "P3", "P4", "O1"],
            "2_0.2_1.8",
            "an imported pool repeating a label",
        ),
        ex_pool("pool_balanced_only", EIGHT[:5], "2_0.2_1.0", "limit = total / 2"),
        ex_pool("pool_offgrid_limit", EIGHT[:4], "2_0.4_1.5", "limit off the grid"),
        ex_pool("pool_too_small", ["F3", "F4", "F3"], "2_0.5_none", "zero montages"),
        ex_bucket(
            "bucket_plain",
            [["F7", "F5"], ["P7"], ["F3"], ["P3", "P5"]],
            "2_0.01_1.99",
            "finest step the Step input allows",
        ),
        ex_bucket(
            "bucket_shared_poles",
            [["A", "B"], ["A", "B"], ["C", "A"], ["D"]],
            "2_0.05_1.95",
            "an electrode in both poles of a channel and in the other channel",
        ),
        ex_bucket(
            "bucket_self_pair_only",
            [["A"], ["A"], ["B"], ["C"]],
            "2_0.5_none",
            "the only montage has a zero-field channel: nothing to run",
        ),
        ex_bucket(
            "bucket_limit_below_half",
            [["A"], ["B"], ["C"], ["D"]],
            "2_0.2_0.8",
            "channel limit below total / 2: no split",
        ),
        ex_bucket(
            "bucket_repeated_label",
            [["A", "A", "B"], ["C"], ["D"], ["E"]],
            "2_0.4_1.6",
            "a label listed twice in one bucket is one electrode",
        ),
        ex_bucket(
            "bucket_same_four",
            [["A", "B", "C", "D"]] * 4,
            "2_0.4_1.6",
            "every bucket the same: each montage once, like pool mode",
        ),
        ex_bucket(
            "bucket_same_four_asymmetric",
            [["A", "B", "C", "D"]] * 4,
            "2_0.4_1.5",
            "split list not its own mirror: both channel orders count",
        ),
        ex_bucket(
            "bucket_cross_channel_overlap",
            [["A", "B", "C"], ["D", "E"], ["B", "D", "F"], ["A", "E", "C", "G"]],
            "2_0.5_none",
            "buckets overlapping across poles and channels",
        ),
        mex_bucket(
            "mex_same_eight",
            [EIGHT] * 8,
            "audit: the desktop showed 8^8 = 16,777,216, the runner evaluates 8! = 40,320",
        ),
        mex_bucket(
            "mex_same_four",
            [EIGHT[:4]] * 8,
            "eight buckets of the same four electrodes cannot make 8 distinct",
        ),
        mex_bucket(
            "mex_singletons",
            [[e] for e in EIGHT],
            "one electrode per bucket",
        ),
        mex_bucket(
            "mex_shared_poles",
            [["A", "B"], ["A", "B"], ["C"], ["D"], ["E"], ["F"], ["G"], ["H"]],
            "pair 1's poles share two electrodes",
        ),
    ]


def main() -> None:
    OUT.write_text(json.dumps({"cases": cases()}, indent=1) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
