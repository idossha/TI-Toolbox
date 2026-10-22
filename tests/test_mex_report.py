"""mEx searches write a four-channel report and keep all four channel currents.

Pins (2026-10-22):

* ``run_m_ex_search`` never called a report writer (the ex runner does), so an mEx run had no page.
  It now calls ``create_ex_search_report`` once with the project, subject and its own run folder,
  and a report that cannot be written still never fails the run.
* ``build_csv_rows`` wrote ``Current_Ch1_mA``/``Current_Ch2_mA`` only, although the mEx engine
  records ``current_ch1_mA`` .. ``current_ch4_mA``; an mEx ``final_output.csv`` now has all four
  columns, and an ex one keeps exactly its two.
* ``ex_search.build_html`` zipped the pairs with ``[I1, I2]``: a four-pair montage was listed as two
  channels and called a "two-channel combination", and ``top_distinct`` keyed rows on the first two
  pairs, folding two montages that differ only in pairs 3-4 into one. The page now lists one row per
  pair at its current (an older mEx CSV without Ch3/Ch4 takes the run's one ``current_mA``), and
  states no current sweep for a search that has none.

Expected values come from the montage strings and ``current_mA`` written into the fixtures here
(``A_B <> C_D <> E_F <> G_H_I-1.0mA`` is four pairs; 4 x 1 mA = 4 mA total).

Reproduce: ``.venv/bin/python -m pytest tests/test_mex_report.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TAIL = "TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index"
_OLD_HEADER = f"Montage,Current_Ch1_mA,Current_Ch2_mA,{_TAIL}"


def _mex_run(tmp_path: Path, lines: list[str], header: str = _OLD_HEADER) -> Path:
    run = tmp_path / "mex-run"
    run.mkdir()
    (run / "run_config.json").write_text(
        json.dumps(
            {
                "subject_id": "X",
                "roi_name": "thal.csv",
                "roi_radius": 3.0,
                "leadfield_hdf": "X_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
                "electrode_mode": "pool",
                "electrodes": {"electrodes": list("ABCDEFGHIJKL")},
                "n_combinations": len(lines),
                "current_mA": 1.0,
            }
        )
    )
    (run / "final_output.csv").write_text("\n".join([header, *lines]) + "\n")
    return run


def _html(run: Path) -> str:
    from tit.reporting.generators import ex_search

    with patch("tit.tools.montage_visualizer.montage_webp", return_value=None):
        return ex_search.build_html(ex_search.collect(run), "X")


def _text(fragment: str) -> str:
    return re.sub(r"<[^>]+>", " ", fragment)


def _section(html: str, sid: str) -> str:
    return html.split(f'id="{sid}"', 1)[1].split("</section>", 1)[0]


_FOUR = "A_B <> C_D <> E_F <> G_H_I-1.0mA,1.0,1.0,0.4,0.2,0.1,2.0,0.4"


def test_read_results_keeps_all_four_pairs(tmp_path):
    from tit.reporting.generators import ex_search

    run = _mex_run(tmp_path, [_FOUR])
    (row,) = ex_search.read_results(run / "final_output.csv")
    assert row["pairs"] == [["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]]


def test_the_page_lists_four_channels_at_the_runs_current(tmp_path):
    html = _html(_mex_run(tmp_path, [_FOUR]))
    winner = _section(html, "winner")
    channels = re.findall(r"<dt>Channel (\d)</dt><dd>([^<]*)</dd>", winner)
    assert [int(k) for k, _ in channels] == [1, 2, 3, 4]  # == len(pairs)
    assert [v for _, v in channels] == [
        "A → B, 1 mA",
        "C → D, 1 mA",
        "E → F, 1 mA",
        "G → H, 1 mA",
    ]
    assert "1 mA per channel, 4 mA total" in _text(winner)
    assert "two-channel" not in html
    assert "four-channel" in _text(_section(html, "technical"))
    # An mEx search has no current sweep; nothing may claim a 0 mA one.
    assert "0 mA total" not in _text(winner) and "at most 0 mA" not in _text(winner)


def test_the_top_table_has_a_column_per_channel(tmp_path):
    html = _html(_mex_run(tmp_path, [_FOUR]))
    table = html.split("Top 25 by composite", 1)[1].split("</table>", 1)[0]
    heads = re.findall(r"<th[^>]*>([^<]*)</th>", table)
    assert [h for h in heads if h.startswith("Channel")] == [
        "Channel 1",
        "Channel 2",
        "Channel 3",
        "Channel 4",
    ]
    (body,) = re.findall(r"<tbody>(.*?)</tbody>", table)
    cells = [_text(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", body)]
    assert cells[1:6] == ["A–B", "C–D", "E–F", "G–H", "1 / 1 / 1 / 1"]


def test_montages_that_differ_only_in_pairs_three_and_four_are_both_ranked(tmp_path):
    html = _html(
        _mex_run(
            tmp_path,
            [
                "A_B <> C_D <> E_F <> G_H_I-1.0mA,1.0,1.0,0.4,0.2,0.1,2.0,0.4",
                "A_B <> C_D <> I_J <> K_L_I-1.0mA,1.0,1.0,0.3,0.15,0.1,1.5,0.225",
            ],
        )
    )
    table = html.split("Top 25 by composite", 1)[1].split("</table>", 1)[0]
    assert table.count("<tr>") == 1 + 2  # header + both montages
    assert "I–J" in table and "K–L" in table


def test_four_current_columns_are_read_when_the_csv_has_them(tmp_path):
    header = (
        "Montage,Current_Ch1_mA,Current_Ch2_mA,Current_Ch3_mA,Current_Ch4_mA," + _TAIL
    )
    run = _mex_run(
        tmp_path,
        ["A_B <> C_D <> E_F <> G_H_I-1.0mA,1.0,1.0,1.0,1.0,0.4,0.2,0.1,2.0,0.4"],
        header=header,
    )
    winner = _section(_html(run), "winner")
    assert len(re.findall(r"<dt>Channel \d</dt>", winner)) == 4


# ── the CSV writer ──────────────────────────────────────────────────────


def _metrics(**currents):
    return {
        "R_TImax_ROI": 0.4,
        "R_TImean_ROI": 0.2,
        "R_TImean_GM": 0.1,
        "R_Focality": 2.0,
        **currents,
    }


def _written(rows) -> list[dict]:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return list(csv.DictReader(io.StringIO(out.getvalue())))


def test_mex_csv_rows_carry_all_four_channel_currents():
    from tit.opt.ex.results import build_csv_rows

    results = {
        "TI_field_A_B_and_C_D_and_E_F_and_G_H_I-0.25mA.msh": _metrics(
            current_ch1_mA=0.25,
            current_ch2_mA=0.25,
            current_ch3_mA=0.25,
            current_ch4_mA=0.25,
        )
    }
    rows, *_ = build_csv_rows(results, "R")
    (row,) = _written(rows)
    assert [row[f"Current_Ch{k}_mA"] for k in (1, 2, 3, 4)] == ["0.25"] * 4
    assert row["Montage"] == "A_B <> C_D <> E_F <> G_H_I-0.25mA"


def test_ex_csv_rows_keep_exactly_two_current_columns():
    from tit.opt.ex.results import build_csv_rows

    results = {
        "TI_field_A_B_and_C_D_I1-1.5mA_I2-0.5mA.msh": _metrics(
            current_ch1_mA=1.5, current_ch2_mA=0.5
        )
    }
    rows, *_ = build_csv_rows(results, "R")
    assert rows[0] == [
        "Montage",
        "Current_Ch1_mA",
        "Current_Ch2_mA",
        "TImax_ROI",
        "TImean_ROI",
        "TImean_GM",
        "Focality",
        "Composite_Index",
    ]


# ── the runner ──────────────────────────────────────────────────────────


def _pm(tmp_path):
    pm = MagicMock()
    pm.project_dir = str(tmp_path / "project")
    pm.logs.return_value = str(tmp_path / "logs")
    pm.m_ex_search_run.return_value = str(tmp_path / "mex-out")
    pm.rois.return_value = str(tmp_path / "rois")
    pm.m2m.return_value = str(tmp_path / "m2m_001")
    return pm


def _mex_config():
    from tit.opt.config import MExConfig

    return MExConfig(
        subject_id="001",
        leadfield_hdf="001_leadfield_NET.hdf5",
        roi_name="motor.csv",
        electrodes=MExConfig.PoolElectrodes(electrodes=list("ABCDEFGH")),
        current_mA=1.0,
    )


@patch("tit.opt.mex.mex.process_and_save")
@patch("tit.opt.mex.mex.MExSearchEngine")
@patch("tit.opt.mex.mex.add_file_handler")
@patch("tit.opt.mex.mex.get_path_manager")
def test_run_m_ex_search_writes_its_report_once(
    mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
):
    from tit.opt.mex.mex import run_m_ex_search

    mock_gpm.return_value = _pm(tmp_path)
    mock_engine_cls.return_value.run.return_value = {"m1": {}}
    mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}
    with patch(
        "tit.reporting.generators.ex_search.create_ex_search_report",
        return_value=Path("/r.html"),
    ) as create:
        result = run_m_ex_search(_mex_config())
    create.assert_called_once_with(
        str(tmp_path / "project"), "001", str(tmp_path / "mex-out")
    )
    assert result.success is True


@patch("tit.opt.mex.mex.process_and_save")
@patch("tit.opt.mex.mex.MExSearchEngine")
@patch("tit.opt.mex.mex.add_file_handler")
@patch("tit.opt.mex.mex.get_path_manager")
def test_a_failing_mex_report_never_fails_the_run(
    mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
):
    from tit.opt.mex.mex import run_m_ex_search

    mock_gpm.return_value = _pm(tmp_path)
    mock_engine_cls.return_value.run.return_value = {"m1": {}}
    mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}
    with patch(
        "tit.reporting.generators.ex_search.create_ex_search_report",
        side_effect=OSError("disk full"),
    ) as create:
        result = run_m_ex_search(_mex_config())
    assert create.call_count == 1
    assert result.success is True and result.results_csv == "/c"
