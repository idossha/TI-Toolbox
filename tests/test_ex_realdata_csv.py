"""Real Dataset 000 ex/mEx-search outputs satisfy counting, metric identities and TI physics.

What this pins (2026-10-22), over every ``derivatives/SimNIBS/sub-*/{ex,m-ex}-search/<run>/``
that has a ``run_config.json``, read-only:

* Counting. ``final_output.csv`` has ``run_config.n_combinations`` rows and no repeated
  ``Montage``; its montages are exactly an enumeration written here with ``itertools`` from the
  recorded electrodes and current sweep (bucket mode: the product of the buckets with four (or
  eight) distinct electrodes, times every split; pool mode: every physical montage -- a 4-subset,
  one of its 3 pairings, each pair at its current -- each appearing equally often: once since
  pool mode evaluates each physical montage once (``tit/opt/ex/logic.py``), 8 times in runs
  written before that, which listed both polarities of both pairs in both channel orders).
  Every electrode sits in the bucket its position demands.
* Currents. Ch1 + Ch2 = the recorded total, each in [step, channel limit] and equal to the
  currents in the montage name (ex); every channel at ``current_mA`` (mEx).
* Metric identities. ``0 <= TImean_ROI <= TImax_ROI``; ``Focality = TImean_ROI / TImean_GM`` and
  ``Composite_Index = TImean_ROI * Focality`` (``tit/opt/ex/engine.py``/``results.py``), checked
  with interval arithmetic over the CSV's 4-decimal rounding (each written value is within
  5e-5 of the one computed), not a guessed tolerance.
* TI physics. The envelope is degree-1 homogeneous and non-decreasing in each channel's
  amplitude (``max_n 2*min(|E1.n|, |E2.n|)``), so for two splits of one physical montage with
  per-pair current ratios k1, k2: ``min(k1,k2) <= M_a / M_b <= max(k1,k2)`` for TImax, TImean and
  the GM mean (positive-weight means and maxima keep the bound), again over the rounding
  interval. Rows that are symmetry images of one montage (legacy pool runs) agree to one
  rounding unit. The GM mean does not depend on the ROI, so runs of one subject and leadfield
  agree on it montage by montage. Plausibility: ``0 < TImean_GM < 1 V/m`` at <= 4 mA in total.

Where the numbers come from: the files themselves and the recorded config; nothing is retyped.
Probed true on the four runs present on 2026-10-22 (three sub-101 pool runs, 480 rows each,
written before one-row-per-montage; sub-ernie ``film_thalamus_bilateral_jurak``, 47 916 rows).

Gate: ``TIT_DATASET_000`` = a Dataset 000 copy (skips with a reason when unset or absent). The
files read are listed with their mtime and size before and after, and must not change.
Reproduce: ``TIT_DATASET_000=/Users/idohaber/datasets/000 .venv/bin/python -m pytest
tests/test_ex_realdata_csv.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from itertools import combinations, permutations, product
from math import comb
from pathlib import Path

import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
pytestmark = pytest.mark.skipif(
    not ROOT or not os.path.isdir(os.path.join(ROOT, "derivatives", "SimNIBS")),
    reason="skipping: TIT_DATASET_000 is unset or has no derivatives/SimNIBS",
)

#: Half a unit of the CSV's 4-decimal rounding: the written value is within this of the true one.
HALF = 5e-5
METRICS = ("TImax_ROI", "TImean_ROI", "TImean_GM")


def _run_dirs() -> list[Path]:
    base = Path(ROOT) / "derivatives" / "SimNIBS"
    found = sorted(base.glob("sub-*/ex-search/*/run_config.json")) + sorted(
        base.glob("sub-*/m-ex-search/*/run_config.json")
    )
    return [p.parent for p in found]


def _parse_montage(name: str, n_pairs: int) -> tuple[list[str], list[float] | None]:
    """Electrodes and (ex) the currents written into a Montage cell, parsed independently."""
    pairs = name.split(" <> ")
    assert len(pairs) == n_pairs, name
    last = pairs[-1].split("_")
    currents = None
    if n_pairs == 2:  # ..._I1-1.5mA_I2-0.5mA
        assert last[-2].startswith("I1-") and last[-1].startswith("I2-"), name
        currents = [float(last[-2][3:-2]), float(last[-1][3:-2])]
        last = last[:-2]
    else:  # ..._I-1.0mA
        assert last[-1].startswith("I-"), name
        last = last[:-1]
    pairs[-1] = "_".join(last)
    electrodes = []
    for pair in pairs:
        a, b = pair.split("_")
        electrodes += [a, b]
    return electrodes, currents


def _splits(
    total: float, step: float, limit: float | None
) -> list[tuple[float, float]]:
    """Every (ch1, ch2) on the step grid summing to total, each in [step, limit]."""
    limit = limit or total - step
    n = round(total / step)
    out = []
    for k in range(1, n):
        ch1, ch2 = k * step, (n - k) * step
        if ch1 <= limit + 1e-9 and ch2 <= limit + 1e-9:
            out.append((round(ch1, 6), round(ch2, 6)))
    return out


def _load(run: Path) -> dict:
    cfg = json.loads((run / "run_config.json").read_text())
    kind = "mex" if run.parent.name == "m-ex-search" else "ex"
    n_pairs = 4 if kind == "mex" else 2
    rows = []
    with open(run / "final_output.csv", newline="") as f:
        for r in csv.DictReader(f):
            electrodes, named = _parse_montage(r["Montage"], n_pairs)
            currents = [
                float(r[f"Current_Ch{k}_mA"])
                for k in range(1, n_pairs + 1)
                if r.get(f"Current_Ch{k}_mA") not in (None, "")
            ]
            rows.append(
                {
                    "montage": r["Montage"],
                    "electrodes": electrodes,
                    "named": named,
                    "currents": currents,
                    **{
                        k: float(r[k])
                        for k in (*METRICS, "Focality", "Composite_Index")
                    },
                }
            )
    return {"dir": run, "cfg": cfg, "kind": kind, "rows": rows}


def _snapshot(runs: list[Path]) -> dict[str, tuple[int, int]]:
    out = {}
    for run in runs:
        for name in ("run_config.json", "final_output.csv"):
            st = (run / name).stat()
            out[str(run / name)] = (st.st_mtime_ns, st.st_size)
    return out


@pytest.fixture(scope="module")
def runs():
    dirs = _run_dirs()
    before = _snapshot(dirs)
    loaded = [_load(d) for d in dirs]
    yield loaded
    assert _snapshot(dirs) == before, "Dataset 000 files changed while being read"


def _class_key(row: dict) -> frozenset:
    """A physical ex montage: each unordered pair with its current."""
    e = row["electrodes"]
    return frozenset(
        {
            (frozenset(e[0:2]), round(row["currents"][0], 6)),
            (frozenset(e[2:4]), round(row["currents"][1], 6)),
        }
    )


def test_there_are_runs_to_check(runs):
    assert runs, f"no ex/m-ex-search run with run_config.json under {ROOT}"
    assert all(r["rows"] for r in runs)


def test_row_counts_and_enumeration_match_the_recorded_search(runs):
    for run in runs:
        cfg, rows, where = run["cfg"], run["rows"], run["dir"]
        assert len(rows) == cfg["n_combinations"], where
        assert len({r["montage"] for r in rows}) == len(
            rows
        ), f"{where}: repeated Montage"
        n_pairs = 4 if run["kind"] == "mex" else 2
        if run["kind"] == "ex":
            splits = _splits(
                cfg["total_current_mA"], cfg["current_step_mA"], cfg["channel_limit_mA"]
            )
            assert splits, where
        electrodes = cfg["electrodes"]
        if cfg["electrode_mode"] == "bucket":
            keys = [
                f"e{k}_{s}" for k in range(1, n_pairs + 1) for s in ("plus", "minus")
            ]
            buckets = [list(dict.fromkeys(electrodes[k])) for k in keys]
            for r in rows:
                for label, bucket, key in zip(r["electrodes"], buckets, keys):
                    assert label in bucket, f"{where}: {label} not in {key}"
            got = Counter(
                (tuple(r["electrodes"]), tuple(round(c, 6) for c in r["currents"][:2]))
                for r in rows
            )
            assert max(got.values()) == 1, where
            if cfg.get("symmetric_bucket"):
                continue  # a mirrored subset of the product; membership checked above
            quads = [q for q in product(*buckets) if len(set(q)) == len(q)]
            if run["kind"] == "ex":
                expected = {(q, s) for q in quads for s in splits}
            else:
                cur = round(cfg["current_mA"], 6)
                expected = {(q, (cur, cur)) for q in quads}
            assert set(got) == expected, where
        elif run["kind"] == "ex":
            pool = list(dict.fromkeys(electrodes["electrodes"]))
            for r in rows:
                assert set(r["electrodes"]) <= set(pool), where
            expected = set()
            for a, b, c, d in combinations(pool, 4):
                for p, q in (((a, b), (c, d)), ((a, c), (b, d)), ((a, d), (b, c))):
                    for i1, i2 in splits:
                        for x, y in ((p, q), (q, p)):
                            expected.add(
                                frozenset({(frozenset(x), i1), (frozenset(y), i2)})
                            )
            classes = Counter(_class_key(r) for r in rows)
            assert set(classes) == expected, where
            multiplicity = set(classes.values())
            # 1: one row per physical montage (today); 8: every electrode ordering (legacy).
            assert multiplicity in ({1}, {8}), f"{where}: {multiplicity}"
        else:
            pool = list(dict.fromkeys(electrodes["electrodes"]))
            assert (
                len(rows)
                == comb(len(pool), 8) * len(list(permutations(range(8)))) // 64
            ), where


def test_currents_follow_the_recorded_sweep(runs):
    for run in runs:
        cfg, where = run["cfg"], run["dir"]
        for r in run["rows"]:
            if run["kind"] == "ex":
                i1, i2 = r["currents"]
                assert [i1, i2] == r["named"], f"{where}: {r['montage']}"
                assert i1 + i2 == pytest.approx(cfg["total_current_mA"], abs=1e-6)
                limit = cfg["channel_limit_mA"] or cfg["total_current_mA"]
                for i in (i1, i2):
                    assert cfg["current_step_mA"] - 1e-6 <= i <= limit + 1e-6, where
            elif len(r["currents"]) == 4:  # mEx CSVs before 2026-10-22 kept 2 columns
                assert r["currents"] == [pytest.approx(cfg["current_mA"])] * 4, where


def test_metric_identities_hold_within_the_csv_rounding(runs):
    for run in runs:
        where = run["dir"]
        for r in run["rows"]:
            tmax, tmean, gm = r["TImax_ROI"], r["TImean_ROI"], r["TImean_GM"]
            foc, compo = r["Focality"], r["Composite_Index"]
            assert 0 <= tmean <= tmax, f"{where}: {r['montage']}"
            # Focality = TImean/GM, each true value within HALF of the written one.
            lo = (tmean - HALF) / (gm + HALF)
            hi = (tmean + HALF) / (gm - HALF)
            assert lo - HALF <= foc <= hi + HALF, f"{where}: {r['montage']}"
            # Composite = TImean * Focality (true values), with the same intervals.
            lo = max(tmean - HALF, 0) * max(foc - HALF, 0)
            hi = (tmean + HALF) * (foc + HALF)
            assert lo - HALF <= compo <= hi + HALF, f"{where}: {r['montage']}"


def test_the_envelope_is_homogeneous_and_monotone_in_the_channel_currents(runs):
    checks = 0
    for run in [r for r in runs if r["kind"] == "ex"]:
        groups = defaultdict(list)
        for r in run["rows"]:
            e = r["electrodes"]
            pairing = frozenset({frozenset(e[0:2]), frozenset(e[2:4])})
            amps = {
                frozenset(e[0:2]): r["currents"][0],
                frozenset(e[2:4]): r["currents"][1],
            }
            groups[pairing].append((amps, r))
        for members in groups.values():
            for (amp_a, a), (amp_b, b) in permutations(members, 2):
                ks = [amp_a[p] / amp_b[p] for p in amp_a]
                kmin, kmax = min(ks), max(ks)
                for m in METRICS:
                    assert a[m] - HALF <= kmax * (b[m] + HALF), (run["dir"], a, b, m)
                    assert a[m] + HALF >= kmin * (b[m] - HALF), (run["dir"], a, b, m)
                    checks += 1
    assert checks, "no two splits of one montage to compare"


def test_symmetry_images_of_one_montage_score_alike(runs):
    for run in [r for r in runs if r["kind"] == "ex"]:
        by_class = defaultdict(list)
        for r in run["rows"]:
            by_class[_class_key(r)].append(r)
        for rows in by_class.values():
            for r in rows[1:]:
                for m in (*METRICS, "Focality", "Composite_Index"):
                    # One unit of the last written digit: a float tail may straddle a boundary.
                    assert abs(r[m] - rows[0][m]) <= 2 * HALF + 1e-12, (run["dir"], m)


def test_the_grey_matter_mean_is_the_same_whatever_the_roi(runs):
    by_leadfield = defaultdict(list)
    for run in [r for r in runs if r["kind"] == "ex"]:
        cfg = run["cfg"]
        by_leadfield[(cfg["subject_id"], Path(cfg["leadfield_hdf"]).name)].append(run)
    shared = [group for group in by_leadfield.values() if len(group) > 1]
    if not shared:
        pytest.skip("skipping: no two ex runs share a subject and a leadfield")
    compared = 0
    for group in shared:
        per_run = []
        for run in group:
            values = defaultdict(list)
            for r in run["rows"]:
                values[_class_key(r)].append(r["TImean_GM"])
            per_run.append(values)
        for key in set.intersection(*(set(v) for v in per_run)):
            seen = [gm for values in per_run for gm in values[key]]
            assert max(seen) - min(seen) <= 2 * HALF + 1e-12, key
            compared += 1
    assert compared


def test_grey_matter_means_are_plausible(runs):
    for run in runs:
        cfg = run["cfg"]
        total = (
            cfg["total_current_mA"] if run["kind"] == "ex" else 4 * cfg["current_mA"]
        )
        if total > 4:
            continue
        for r in run["rows"]:
            assert 0 < r["TImean_GM"] < 1.0, (run["dir"], r["montage"])
