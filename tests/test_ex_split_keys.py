"""Every current split the ex/mEx engines evaluate reaches the CSV and the replay unrounded.

What this pins (2026-10-22, package p05 "ex-split-key-collision"):

* ``ExSearchEngine.run`` returns one result per (montage, split): the result key must not
  collapse two splits that agree to one decimal (step 0.05 used to keep 20 of 39 splits).
* ``final_output.csv`` carries the evaluated currents, not a ``.1f`` rounding of them
  (step 0.25 used to write 1.75 / 0.25 mA as 1.8 / 0.2).
* The candidate replay (``tit.opt.candidate_catalog.candidate_detail``) turns a row back into
  the simulation that was scored: ex 1.75 / 0.25 mA, mEx 0.25 mA on all four pairs -- also for
  an mEx run written before the fix (hand-typed legacy CSV with 0.2 / 0.2), whose replay takes
  the pair current from ``run_config.json``; a legacy ex row replays its CSV split as written.

Where the numbers come from: the arithmetic spec of the sweep -- ``c1 + c2 = total`` with
``c1`` walking down from the channel limit in ``step`` increments and both channels at least one
step -- written out by hand below (``_hand_splits``), not read from ``generate_current_ratios``.
The fields come from a tiny random leadfield and the engine scores them with
``tit.calc.envelope_max`` (real numpy), so nothing here depends on SimNIBS.

Reproduce: ``pytest tests/test_ex_split_keys.py -q``.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tit.opt import candidate_catalog as catalog
from tit.opt.ex.engine import ExSearchEngine
from tit.opt.ex.logic import generate_current_ratios
from tit.opt.ex.results import save_csv
from tit.opt.mex.engine import MExSearchEngine

LABELS = ["A", "B", "C", "D", "E", "F", "G", "H"]
ROI = "target"


class _FakeTI:
    """The two SimNIBS TI_utils calls the engines make, on a plain numpy leadfield."""

    @staticmethod
    def get_field(spec, leadfield, idx):
        plus, minus, current = spec
        return current * (leadfield[idx.index(plus)] - leadfield[idx.index(minus)])


@pytest.fixture
def fake_ti(monkeypatch):
    monkeypatch.setattr("tit.opt.ex.engine.TI", _FakeTI)
    monkeypatch.setattr("tit.opt.mex.engine.TI", _FakeTI)


def _engine(cls):
    engine = cls("unused.hdf5", "roi.csv", ROI, logging.getLogger("test.ex.keys"))
    rng = np.random.default_rng(7)
    engine.leadfield = rng.normal(size=(len(LABELS), 20, 3))
    engine.idx_lf = list(LABELS)
    engine.roi_indices = np.arange(5)
    engine.roi_volumes = np.ones(5)
    engine.gm_indices = np.arange(20)
    engine.gm_volumes = np.ones(20)
    return engine


def _hand_splits(total: float, step: float, count: int) -> list[tuple[float, float]]:
    """``(c1, total - c1)`` for c1 = (total - step), (total - 2 step), ... -- *count* of them."""
    return [
        (round(total - step * (k + 1), 9), round(step * (k + 1), 9))
        for k in range(count)
    ]


def _run_ex(engine, ratios, tmp_path):
    return engine.run(
        ["A"], ["B"], ["C"], ["D"], ratios, False, str(tmp_path), n_jobs=1
    )


def _csv_currents(path: Path, n: int) -> list[tuple[float, ...]]:
    with path.open(newline="") as stream:
        return [
            tuple(float(row[f"Current_Ch{i}_mA"]) for i in range(1, n + 1))
            for row in csv.DictReader(stream)
        ]


def _same_pairs(got, expected, tol=1e-9) -> bool:
    if len(got) != len(expected):
        return False
    remaining = list(expected)
    for pair in got:
        match = next(
            (e for e in remaining if all(abs(a - b) <= tol for a, b in zip(pair, e))),
            None,
        )
        if match is None:
            return False
        remaining.remove(match)
    return True


# step 0.05 on 2 mA: c1 = 1.95, 1.90, ..., 0.05 -> 39 splits (hand count: (2 - 0.05) / 0.05).
STEP_005 = _hand_splits(2.0, 0.05, 39)


def test_every_005_split_is_a_separate_result(fake_ti, tmp_path):
    ratios = generate_current_ratios(2.0, 0.05, 1.95)
    results = _run_ex(_engine(ExSearchEngine), ratios, tmp_path)
    assert len(results) == 39
    evaluated = [(r["current_ch1_mA"], r["current_ch2_mA"]) for r in results.values()]
    assert _same_pairs(evaluated, STEP_005)


def test_csv_carries_the_evaluated_currents(fake_ti, tmp_path):
    ratios = generate_current_ratios(2.0, 0.05, 1.95)
    results = _run_ex(_engine(ExSearchEngine), ratios, tmp_path)
    path = Path(save_csv(results, ROI, str(tmp_path), logging.getLogger("t")))
    written = _csv_currents(path, 2)
    assert _same_pairs(written, STEP_005)
    # Each row names its own split: the montage strings are all different.
    with path.open(newline="") as stream:
        montages = [row["Montage"] for row in csv.DictReader(stream)]
    assert len(set(montages)) == 39


# Total 2 mA: steps the desktop Step input accepts and their hand-counted split totals
# (c1 from total - step down to step; 0.15: 1.85..0.20 is 12; 0.3: 1.7..0.5 is 5).
SPLITS_PER_STEP = {0.01: 199, 0.05: 39, 0.1: 19, 0.15: 12, 0.25: 7, 0.3: 5, 0.5: 3}


@pytest.mark.parametrize("step", sorted(SPLITS_PER_STEP))
def test_distinct_result_keys_equal_the_number_of_splits(fake_ti, tmp_path, step):
    ratios = generate_current_ratios(2.0, step, 2.0 - step)
    assert len(ratios) == SPLITS_PER_STEP[step]
    results = _run_ex(_engine(ExSearchEngine), ratios, tmp_path)
    assert len(results) == SPLITS_PER_STEP[step]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr("tit.catalog.subject_ids", lambda pm: ["ernie"])
    return SimpleNamespace(
        project_dir=str(tmp_path),
        flex_search_run=lambda subject, run: tmp_path / "flex" / run,
        ex_search_run=lambda subject, run: tmp_path / "ex" / run,
        m_ex_search_run=lambda subject, run: tmp_path / "mex" / run,
    )


def _write_run(directory: Path, results: dict, config: dict) -> None:
    directory.mkdir(parents=True)
    save_csv(results, ROI, str(directory), logging.getLogger("t"))
    (directory / "run_config.json").write_text(json.dumps(config))


def test_ex_replay_uses_the_quarter_milliamp_split(fake_ti, project, tmp_path):
    ratios = generate_current_ratios(2.0, 0.25, 1.75)
    results = _run_ex(_engine(ExSearchEngine), ratios, tmp_path)
    run = Path(project.ex_search_run("ernie", "run"))
    _write_run(
        run,
        results,
        {"subject_id": "ernie", "leadfield_hdf": "ernie_leadfield_EEG10-10.hdf5"},
    )
    replayed = [
        tuple(
            catalog.candidate_detail(project, "ernie", "ex", "run", f"ex-{i}")[
                "simulation_config"
            ]["intensities"]
        )
        for i in range(len(results))
    ]
    # 0.25 mA steps on 2 mA: 1.75/0.25, 1.5/0.5, 1.25/0.75, 1/1, 0.75/1.25, 0.5/1.5, 0.25/1.75.
    assert _same_pairs(replayed, _hand_splits(2.0, 0.25, 7))


def test_mex_replay_drives_all_four_pairs_at_the_configured_current(
    fake_ti, project, tmp_path
):
    engine = _engine(MExSearchEngine)
    buckets = dict(
        zip(
            [
                "e1_plus",
                "e1_minus",
                "e2_plus",
                "e2_minus",
                "e3_plus",
                "e3_minus",
                "e4_plus",
                "e4_minus",
            ],
            [[label] for label in LABELS],
        )
    )
    results = engine.run(buckets, False, str(tmp_path), current_mA=0.25, n_jobs=1)
    assert len(results) == 1
    run = Path(project.m_ex_search_run("ernie", "run"))
    _write_run(
        run,
        results,
        {
            "subject_id": "ernie",
            "leadfield_hdf": "ernie_leadfield_EEG10-10.hdf5",
            "current_mA": 0.25,
        },
    )
    assert _csv_currents(run / "final_output.csv", 2) == [(0.25, 0.25)]
    with (run / "final_output.csv").open(newline="") as stream:
        (row,) = list(csv.DictReader(stream))
    # The montage name carries the pair current too (".1f" wrote 0.25 mA as "I-0.2mA").
    assert row["Montage"] == "A_B <> C_D <> E_F <> G_H_I-0.25mA"
    detail = catalog.candidate_detail(project, "ernie", "mex", "run", "ex-0")
    assert detail["simulation_config"]["intensities"] == [0.25, 0.25, 0.25, 0.25]


# A final_output.csv as the pre-2026-10-22 writer left it (".1f" currents and names), typed by
# hand: header of tit/opt/ex/results.py build_csv_rows, metric cells arbitrary but valid.
_LEGACY_HEADER = (
    "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,"
    "Focality,Composite_Index\n"
)


def _write_legacy_run(directory: Path, rows: list[str], config: dict) -> None:
    directory.mkdir(parents=True)
    (directory / "final_output.csv").write_text(_LEGACY_HEADER + "".join(rows))
    (directory / "run_config.json").write_text(json.dumps(config))


def test_legacy_mex_run_replays_the_configured_current_on_every_pair(project):
    # mEx at 0.25 mA per pair: the old writer rounded the CSV columns and the name to 0.2,
    # and has no Current_Ch3/Ch4 columns at all.
    run = Path(project.m_ex_search_run("ernie", "legacy"))
    _write_legacy_run(
        run,
        [
            "A_B <> C_D <> E_F <> G_H_I-0.2mA,0.2,0.2,0.3000,0.1000,0.0500,2.0000,0.2000\n"
        ],
        {
            "subject_id": "ernie",
            "leadfield_hdf": "ernie_leadfield_EEG10-10.hdf5",
            "current_mA": 0.25,
        },
    )
    detail = catalog.candidate_detail(project, "ernie", "mex", "legacy", "ex-0")
    simulation = detail["simulation_config"]
    assert simulation["intensities"] == [0.25, 0.25, 0.25, 0.25]
    assert simulation["montages"][0]["electrode_pairs"] == [
        ["A", "B"],
        ["C", "D"],
        ["E", "F"],
        ["G", "H"],
    ]


def test_legacy_ex_run_replays_the_csv_currents_as_written(project):
    # Ex has no single configured current: each row's own split is what was scored. A 0.2 mA
    # sweep was exact under ".1f", so the old file's 1.4 / 0.6 is the evaluated split.
    run = Path(project.ex_search_run("ernie", "legacy"))
    _write_legacy_run(
        run,
        [
            "A_B <> C_D_I1-1.4mA_I2-0.6mA,1.4,0.6,0.3000,0.1000,0.0500,2.0000,0.2000\n",
            "A_B <> C_D_I1-0.6mA_I2-1.4mA,0.6,1.4,0.3000,0.1000,0.0500,2.0000,0.2000\n",
        ],
        {
            "subject_id": "ernie",
            "leadfield_hdf": "ernie_leadfield_EEG10-10.hdf5",
            "total_current_mA": 2.0,
            "current_step_mA": 0.2,
            "channel_limit_mA": 1.8,
        },
    )
    replayed = [
        catalog.candidate_detail(project, "ernie", "ex", "legacy", f"ex-{i}")[
            "simulation_config"
        ]
        for i in range(2)
    ]
    assert [s["intensities"] for s in replayed] == [[1.4, 0.6], [0.6, 1.4]]
    assert all(
        s["montages"][0]["electrode_pairs"] == [["A", "B"], ["C", "D"]]
        for s in replayed
    )
