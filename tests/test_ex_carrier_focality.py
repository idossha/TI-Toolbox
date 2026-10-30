"""Ex/mEx report HF focality and TI selectivity per candidate, and never rank on them (2026-10-29).

What this pins
    Every ex (two channels, each current split) and mEx (four channels) candidate carries
    ``HFpeak_Focality`` = volume-weighted ROI mean / GM mean of hf_peak -- the peak carrier field
    of all its channel fields -- over the same ROI/GM elements and volumes as ``Focality``,
    and ``TI_Selectivity`` = ``Focality / HFpeak_Focality``. ``final_output.csv`` gains the two
    columns after ``Composite_Index`` (empty for a result without them), the candidate review
    exposes them as ``hf_peak_focality`` / ``ti_selectivity`` metrics, the ex-search report lists
    them in its top table when the CSV has them, and ``Composite_Index`` is unchanged. An empty
    ROI or GM, or a GM carrier mean of 0, gives ``None`` (an empty cell), never 0.

Where the expectations come from
    hf_peak by brute force: every one of the ``2**F`` sign vectors ``s`` (itertools.product,
    not halved) and ``max_s |sum_c s_c E_c|`` per element; the channel fields are rebuilt from
    the random leadfield as ``current * (lf[plus] - lf[minus])``. Weighted means are explicit
    sums with authored, non-uniform volumes; ROI and GM overlap only partly. ``Focality`` is
    the engine's own value (pinned elsewhere); only the carrier side is checked here.

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_carrier_focality.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import csv
import itertools
import json
import logging
from pathlib import Path

import numpy as np
import pytest

from tit.opt.ex.engine import ExSearchEngine
from tit.opt.ex.results import build_csv_rows, save_csv
from tit.opt.mex.engine import MExSearchEngine

LABELS = ["A", "B", "C", "D", "E", "F", "G", "H"]
ROI = "target"
N = 40
ROI_IDX = np.array([0, 3, 5, 6, 11, 17, 30])
GM_IDX = np.array([2, 3, 5, 8, 9, 11, 14, 20, 21, 25, 30, 33, 39])


class _FakeTI:
    @staticmethod
    def get_field(spec, leadfield, idx):
        plus, minus, current = spec
        return current * (leadfield[idx.index(plus)] - leadfield[idx.index(minus)])


@pytest.fixture
def fake_ti(monkeypatch):
    monkeypatch.setattr("tit.opt.ex.engine.TI", _FakeTI)
    monkeypatch.setattr("tit.opt.mex.engine.TI", _FakeTI)


def _engine(cls):
    engine = cls("unused.hdf5", "roi.csv", ROI, logging.getLogger("test.ex.carrier"))
    rng = np.random.default_rng(2029)
    engine.leadfield = rng.normal(size=(len(LABELS), N, 3))
    engine.idx_lf = list(LABELS)
    engine.roi_indices = ROI_IDX
    engine.roi_volumes = rng.uniform(0.2, 3.0, len(ROI_IDX))
    engine.gm_indices = GM_IDX
    engine.gm_volumes = rng.uniform(0.2, 3.0, len(GM_IDX))
    return engine


def _channel(engine, plus, minus, current_mA):
    lf, idx = engine.leadfield, engine.idx_lf
    return current_mA / 1000.0 * (lf[idx.index(plus)] - lf[idx.index(minus)])


def _brute_peak(fields):
    stack = np.stack(fields)
    return np.max(
        [
            np.linalg.norm(np.einsum("f,fnx->nx", np.array(s), stack), axis=1)
            for s in itertools.product((1.0, -1.0), repeat=len(fields))
        ],
        axis=0,
    )


def _hand_hf_peak_focality(engine, peak):
    roi = (peak[ROI_IDX] * engine.roi_volumes).sum() / engine.roi_volumes.sum()
    gm = (peak[GM_IDX] * engine.gm_volumes).sum() / engine.gm_volumes.sum()
    return roi / gm


def test_ex_candidates_carry_the_brute_force_hf_peak_focality(fake_ti):
    engine = _engine(ExSearchEngine)
    splits = [(1.5, 0.5), (1.0, 1.0), (0.4, 1.6)]
    results = engine.compute_ti_fields("A", "B", "C", "D", splits)
    for (i1, i2), data in zip(splits, results):
        peak = _brute_peak(
            [_channel(engine, "A", "B", i1), _channel(engine, "C", "D", i2)]
        )
        expected = _hand_hf_peak_focality(engine, peak)
        assert data[f"{ROI}_HFpeak_Focality"] == pytest.approx(expected, rel=1e-12)
        assert data[f"{ROI}_TI_Selectivity"] == pytest.approx(
            data[f"{ROI}_Focality"] / expected, rel=1e-12
        )
    # The split changes the carrier mix, so each split has its own HF focality.
    assert len({round(d[f"{ROI}_HFpeak_Focality"], 12) for d in results}) == 3


def test_mex_candidate_uses_all_four_channel_carriers(fake_ti):
    engine = _engine(MExSearchEngine)
    electrodes = ("A", "B", "C", "D", "E", "F", "G", "H")
    data = engine.compute_mti_field(electrodes, 0.75)
    peak = _brute_peak(
        [_channel(engine, electrodes[k], electrodes[k + 1], 0.75) for k in (0, 2, 4, 6)]
    )
    expected = _hand_hf_peak_focality(engine, peak)
    assert data[f"{ROI}_HFpeak_Focality"] == pytest.approx(expected, rel=1e-12)
    assert data[f"{ROI}_TI_Selectivity"] == pytest.approx(
        data[f"{ROI}_Focality"] / expected, rel=1e-12
    )


def test_csv_appends_the_columns_and_keeps_the_composite(fake_ti, tmp_path):
    engine = _engine(ExSearchEngine)
    results = engine.run(["A"], ["B"], ["C"], ["D"], [(1.0, 1.0)], False, str(tmp_path))
    (data,) = results.values()
    path = save_csv(results, ROI, str(tmp_path), logging.getLogger("t"))
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        (row,) = list(reader)
    assert reader.fieldnames[-3:] == [
        "Composite_Index",
        "HFpeak_Focality",
        "TI_Selectivity",
    ]
    assert row["HFpeak_Focality"] == f"{data[f'{ROI}_HFpeak_Focality']:.4f}"
    assert row["TI_Selectivity"] == f"{data[f'{ROI}_TI_Selectivity']:.4f}"
    composite = data[f"{ROI}_TImean_ROI"] * data[f"{ROI}_Focality"]
    assert row["Composite_Index"] == f"{composite:.4f}"


def test_a_result_without_carrier_metrics_writes_empty_cells():
    results = {
        "TI_field_A_B_and_C_D_I1-1mA_I2-1mA.msh": {
            f"{ROI}_TImax_ROI": 0.4,
            f"{ROI}_TImean_ROI": 0.2,
            f"{ROI}_TImean_GM": 0.1,
            f"{ROI}_Focality": 2.0,
            "current_ch1_mA": 1.0,
            "current_ch2_mA": 1.0,
        }
    }
    rows, *_ = build_csv_rows(results, ROI)
    assert rows[1][-2:] == ["", ""]


def _ex_run(project: Path, csv_text: str) -> None:
    run = project / "derivatives" / "SimNIBS" / "sub-ernie" / "ex-search" / "r1"
    run.mkdir(parents=True)
    (run / "final_output.csv").write_text(csv_text)
    (run / "run_config.json").write_text(
        json.dumps(
            {
                "leadfield_hdf": "/x/ernie_leadfield_GSN-HydroCel-185.hdf5",
                "roi_name": "t.csv",
            }
        )
    )


HEADER = "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index"


def test_candidate_review_exposes_and_sorts_by_the_carrier_metrics(tmp_path):
    from tit.opt import candidate_catalog as catalog
    from tit.paths import get_path_manager

    project = tmp_path / "proj"
    (project / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie").mkdir(
        parents=True
    )
    (project / "dataset_description.json").write_text("{}")
    _ex_run(
        project,
        HEADER
        + ",HFpeak_Focality,TI_Selectivity\n"
        + "A_B <> C_D_I1-1.0mA_I2-1.0mA,1.0,1.0,0.4,0.2,0.1,2.0,0.4,1.25,1.6\n"
        + "A_C <> B_D_I1-1.0mA_I2-1.0mA,1.0,1.0,0.3,0.2,0.1,2.0,0.4,1.6,1.25\n",
    )
    pm = get_path_manager(str(project))
    page = catalog.list_candidates(pm, "ernie", "ex", "r1", sort="ti_selectivity")
    first, second = page["candidates"]
    assert (first["metrics"]["hf_peak_focality"], first["metrics"]["ti_selectivity"]) == (
        1.25,
        1.6,
    )
    assert second["metrics"]["ti_selectivity"] == 1.25
    assert first["metrics"]["contrast"] == 2.0  # Focality, unchanged
    assert "hf_peak" in first["metric_labels"]["hf_peak_focality"]


def test_report_lists_the_columns_only_when_the_csv_has_them(tmp_path):
    from tit.reporting.generators import ex_search

    new = tmp_path / "new.csv"
    new.write_text(
        HEADER
        + ",HFpeak_Focality,TI_Selectivity\n"
        + "A_B <> C_D_I1-1.0mA_I2-1.0mA,1.0,1.0,0.4,0.2,0.1,2.0,0.4,1.25,1.6\n"
    )
    old = tmp_path / "old.csv"
    old.write_text(
        HEADER + "\nA_B <> C_D_I1-1.0mA_I2-1.0mA,1.0,1.0,0.4,0.2,0.1,2.0,0.4\n"
    )
    (row,) = ex_search.read_results(new)
    assert (row["HFpeak_Focality"], row["TI_Selectivity"]) == (1.25, 1.6)
    (legacy,) = ex_search.read_results(old)
    assert legacy["HFpeak_Focality"] is None and legacy["Composite_Index"] == 0.4


def _report_html(tmp_path: Path, csv_text: str) -> str:
    from unittest.mock import patch

    from tit.reporting.generators import ex_search

    run = tmp_path / "run"
    run.mkdir(parents=True)
    (run / "run_config.json").write_text(
        json.dumps(
            {
                "subject_id": "101",
                "roi_name": "thal.csv",
                "leadfield_hdf": "/x/101_leadfield_EEG10-20_extended_SPM12.hdf5",
                "electrode_mode": "pool",
                "electrodes": {"electrodes": ["AF7", "AFz", "CP6", "P10"]},
                "total_current_mA": 2.0,
                "current_step_mA": 0.5,
            }
        )
    )
    (run / "final_output.csv").write_text(csv_text)
    with patch("tit.tools.montage_visualizer.montage_webp", return_value=None):
        return ex_search.build_html(ex_search.collect(run, None), "101")


def test_rendered_report_has_the_columns_only_for_a_csv_with_them(tmp_path):
    row = "AF7_AFz <> CP6_P10_I1-1.0mA_I2-1.0mA,1.0,1.0,0.4,0.2,0.1,2.0,0.4"
    new = _report_html(
        tmp_path / "a", HEADER + ",HFpeak_Focality,TI_Selectivity\n" + row + ",1.25,1.6\n"
    )
    results = new.split('id="results"', 1)[1].split("</section>", 1)[0]
    assert "TI selectivity" in results and ">1.60<" in results and ">1.25<" in results
    old = _report_html(tmp_path / "b", HEADER + "\n" + row + "\n")
    assert "TI selectivity" not in old


@pytest.mark.parametrize("case", ["empty ROI", "empty GM", "zero GM carrier"])
def test_degenerate_candidates_have_no_carrier_metrics_not_zero(fake_ti, case):
    engine = _engine(ExSearchEngine)
    if case == "empty ROI":
        engine.roi_indices, engine.roi_volumes = np.array([], dtype=int), np.array([])
    elif case == "empty GM":
        engine.gm_indices, engine.gm_volumes = np.array([], dtype=int), np.array([])
    else:  # these electrodes put no field on the GM elements
        engine.leadfield[:, GM_IDX] = 0.0
    (data,) = engine.compute_ti_fields("A", "B", "C", "D", [(1.0, 1.0)])
    assert data[f"{ROI}_HFpeak_Focality"] is None
    assert data[f"{ROI}_TI_Selectivity"] is None
    rows, *_ = build_csv_rows({"TI_field_A_B_and_C_D.msh": data}, ROI)
    assert rows[1][-2:] == ["", ""]
